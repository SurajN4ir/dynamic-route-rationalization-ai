"""OSM ingestion pipeline orchestrator.

parse -> validate/normalize -> derive topology (split) -> persist (or, in
dry-run, plan without writing) - see docs/architecture/TASK202_DESIGN.md
§9. This module owns *what* happens; it does not own the transaction
boundary - the caller's session controls commit/rollback (see §12: the
CLI commits only after the whole pipeline returns successfully, and rolls
back on any exception, so a failure never leaves a half-written network).

Dry-run is not a separate/fake code path: every resolver below always
performs its read (existence + diff check) identically in both modes: it
only skips the `session.add()`/attribute-mutation when `dry_run=True`.
That is what makes the reported stats a genuine preview rather than a
guess.
"""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path

from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import Point
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestion.osm.geometry import (
    build_linestring,
    estimate_length_m,
    is_valid_segment_geometry,
)
from app.ingestion.osm.normalize import normalize_ways
from app.ingestion.osm.parser import parse_osm_xml
from app.ingestion.osm.stats import IngestionStats
from app.ingestion.osm.topology import compute_intersection_node_ids, split_way_into_segments
from app.ingestion.osm.types import OSMNode, Rejection, RejectionReason, SegmentCandidate
from app.models.road_network import Intersection, Road, RoadSegment

logger = logging.getLogger(__name__)


async def _resolve_intersection(
    session: AsyncSession, node: OSMNode, *, dry_run: bool, stats: IngestionStats
) -> uuid.UUID:
    existing = await session.scalar(select(Intersection).where(Intersection.osm_node_id == node.id))
    point = Point(node.lon, node.lat)

    if existing is not None:
        existing_point = to_shape(existing.location)
        if not existing_point.equals_exact(point, tolerance=1e-9):
            stats.intersections_updated += 1
            if not dry_run:
                existing.location = from_shape(point, srid=4326)
        return existing.id

    stats.intersections_created += 1
    if dry_run:
        return uuid.uuid4()  # bookkeeping placeholder only - never persisted

    intersection = Intersection(
        location=from_shape(point, srid=4326), source="osm", osm_node_id=node.id
    )
    session.add(intersection)
    await session.flush()
    return intersection.id


async def _resolve_road(
    session: AsyncSession, name: str, *, dry_run: bool, stats: IngestionStats
) -> uuid.UUID:
    existing = await session.scalar(select(Road).where(Road.source == "osm", Road.name == name))
    if existing is not None:
        return existing.id

    stats.roads_created += 1
    if dry_run:
        return uuid.uuid4()

    road = Road(name=name, source="osm")
    session.add(road)
    await session.flush()
    return road.id


async def _resolve_segment(
    session: AsyncSession,
    candidate: SegmentCandidate,
    *,
    nodes_by_id: dict[int, OSMNode],
    node_id_to_intersection_id: dict[int, uuid.UUID],
    road_id: uuid.UUID | None,
    dry_run: bool,
    stats: IngestionStats,
) -> None:
    line = build_linestring(candidate, nodes_by_id)
    if not is_valid_segment_geometry(line):
        stats.rejected_features += 1
        stats.validation_failures += 1
        stats.rejections_by_reason[RejectionReason.INVALID_GEOMETRY.value] += 1
        logger.warning(
            "rejecting segment with invalid geometry",
            extra={"osm_way_id": candidate.osm_way_id, "way_seq": candidate.way_seq},
        )
        return

    length_m = estimate_length_m(line)
    start_id = node_id_to_intersection_id[candidate.start_node_id]
    end_id = node_id_to_intersection_id[candidate.end_node_id]

    existing = await session.scalar(
        select(RoadSegment).where(
            RoadSegment.osm_way_id == candidate.osm_way_id,
            RoadSegment.way_seq == candidate.way_seq,
        )
    )

    if existing is not None:
        existing_shape = to_shape(existing.geometry)
        changed = (
            not existing_shape.equals_exact(line, tolerance=1e-9)
            or existing.is_oneway != candidate.is_oneway
            or existing.road_class != candidate.road_class
            or existing.maxspeed_kph != candidate.maxspeed_kph
            or existing.lanes != candidate.lanes
            or existing.access != candidate.access
            or existing.road_id != road_id
            or existing.start_intersection_id != start_id
            or existing.end_intersection_id != end_id
        )
        if changed:
            stats.segments_updated += 1
            if not dry_run:
                existing.geometry = from_shape(line, srid=4326)
                existing.length_m = length_m
                existing.is_oneway = candidate.is_oneway
                existing.road_class = candidate.road_class
                existing.maxspeed_kph = candidate.maxspeed_kph
                existing.lanes = candidate.lanes
                existing.access = candidate.access
                existing.road_id = road_id
                existing.start_intersection_id = start_id
                existing.end_intersection_id = end_id
        else:
            stats.skipped_duplicates += 1
        return

    stats.segments_created += 1
    if dry_run:
        return

    session.add(
        RoadSegment(
            road_id=road_id,
            start_intersection_id=start_id,
            end_intersection_id=end_id,
            geometry=from_shape(line, srid=4326),
            length_m=length_m,
            is_oneway=candidate.is_oneway,
            road_class=candidate.road_class,
            source="osm",
            osm_way_id=candidate.osm_way_id,
            way_seq=candidate.way_seq,
            access=candidate.access,
            maxspeed_kph=candidate.maxspeed_kph,
            lanes=candidate.lanes,
        )
    )
    await session.flush()


def _log_rejections(rejections: list[Rejection]) -> None:
    for r in rejections:
        logger.info(
            "rejecting way",
            extra={"osm_way_id": r.way_id, "reason": r.reason.value, "detail": r.detail},
        )


async def ingest_osm_file(
    session: AsyncSession,
    path: Path,
    *,
    source: str = "osm",
    dry_run: bool = False,
) -> IngestionStats:
    """Ingests one OSM XML extract into the canonical road network.

    Does not commit or roll back - the caller controls the transaction
    (see module docstring). Safe to call repeatedly with the same input:
    re-running produces the same canonical state (idempotent upsert by
    OSM source id, not blind insert).
    """
    stats = IngestionStats(dry_run=dry_run, source=source, input_path=str(path))
    started = time.monotonic()
    logger.info("osm ingestion starting", extra={"input_path": str(path), "dry_run": dry_run})

    nodes_by_id, raw_ways = parse_osm_xml(path)
    stats.source_features_read = len(raw_ways)

    normalized_ways, rejections = normalize_ways(raw_ways, set(nodes_by_id.keys()))
    stats.eligible_road_features = len(normalized_ways)
    stats.rejected_features += len(rejections)
    stats.validation_failures += len(rejections)
    for r in rejections:
        stats.rejections_by_reason[r.reason.value] += 1
    _log_rejections(rejections)

    intersection_node_ids = compute_intersection_node_ids(normalized_ways)

    node_id_to_intersection_id: dict[int, uuid.UUID] = {}
    for node_id in sorted(intersection_node_ids):
        node_id_to_intersection_id[node_id] = await _resolve_intersection(
            session, nodes_by_id[node_id], dry_run=dry_run, stats=stats
        )

    road_name_to_id: dict[str, uuid.UUID] = {}
    for name in sorted({w.name for w in normalized_ways if w.name}):
        road_name_to_id[name] = await _resolve_road(session, name, dry_run=dry_run, stats=stats)

    for way in normalized_ways:
        road_id = road_name_to_id.get(way.name) if way.name else None
        for candidate in split_way_into_segments(way, intersection_node_ids):
            await _resolve_segment(
                session,
                candidate,
                nodes_by_id=nodes_by_id,
                node_id_to_intersection_id=node_id_to_intersection_id,
                road_id=road_id,
                dry_run=dry_run,
                stats=stats,
            )

    stats.duration_s = time.monotonic() - started
    logger.info("osm ingestion finished", extra=stats.as_dict())
    return stats
