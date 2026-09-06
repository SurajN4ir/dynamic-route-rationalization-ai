"""Builds AURA's canonical directed road graph from PostGIS - see
docs/architecture/TASK203_DESIGN.md.

PostGIS is the system of record (docs/architecture/PHASE2_DESIGN.md); this
module only ever *reads* `intersections`/`road_segments`/`roads` and never
writes anything back. It does not parse OSM, call external map APIs, or
reconstruct topology independently - TASK-202's canonical schema is the
only input.

Two bulk queries, ordered deterministically by primary key, followed by
pure in-memory graph construction - not one query per node/edge (doc
TASK-203 §23 performance guidance). Geometry columns are deliberately not
selected: node coordinates come from `ST_X`/`ST_Y` (two floats, not a WKB
blob) and edge weight comes from the already-cached `length_m` column, so
no shapely/geoalchemy2 geometry parsing happens in this module at all.
"""

from __future__ import annotations

import logging
import time
import uuid

import networkx as nx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.graph.stats import compute_stats
from app.graph.types import GraphBuildResult
from app.models.road_network import Intersection, RoadSegment

logger = logging.getLogger(__name__)


async def _load_nodes(
    session: AsyncSession,
) -> list[tuple[uuid.UUID, int | None, str, float, float]]:
    stmt = select(
        Intersection.id,
        Intersection.osm_node_id,
        Intersection.source,
        func.ST_X(Intersection.location),
        func.ST_Y(Intersection.location),
    ).order_by(Intersection.id)
    result = await session.execute(stmt)
    return [tuple(row) for row in result.all()]


async def _load_edges(
    session: AsyncSession,
) -> list[
    tuple[
        uuid.UUID,
        uuid.UUID | None,
        uuid.UUID,
        uuid.UUID,
        str,
        int | None,
        int | None,
        bool,
        str | None,
        float | None,
        int | None,
        int | None,
        str | None,
    ]
]:
    stmt = select(
        RoadSegment.id,
        RoadSegment.road_id,
        RoadSegment.start_intersection_id,
        RoadSegment.end_intersection_id,
        RoadSegment.source,
        RoadSegment.osm_way_id,
        RoadSegment.way_seq,
        RoadSegment.is_oneway,
        RoadSegment.road_class,
        RoadSegment.length_m,
        RoadSegment.maxspeed_kph,
        RoadSegment.lanes,
        RoadSegment.access,
    ).order_by(RoadSegment.id)
    result = await session.execute(stmt)
    return [tuple(row) for row in result.all()]


async def load_known_intersection_ids(session: AsyncSession) -> set[uuid.UUID]:
    """Independent source of truth for validation - queried separately
    from graph construction so a validation check against this set is a
    real check, not the graph's own node set compared to itself."""
    result = await session.execute(select(Intersection.id))
    return set(result.scalars().all())


async def build_road_graph(session: AsyncSession) -> GraphBuildResult:
    """Builds a fresh `networkx.MultiDiGraph` from the current canonical
    database state. Deterministic: the same database state always
    produces the same nodes, edges, attributes, and iteration order
    (rows are read in primary-key order; Python/NetworkX dicts preserve
    insertion order).

    A `MultiDiGraph`, not a `DiGraph`, because the canonical schema has no
    uniqueness constraint on `(start_intersection_id, end_intersection_id)`
    - two distinct RoadSegments legitimately connecting the same
    intersection pair (e.g. divided carriageways) must remain distinct
    edges, not silently collapsed (doc TASK-203 §14).

    Does not commit, roll back, or otherwise mutate the session - this is
    a pure read.
    """
    started = time.monotonic()
    logger.info("graph build starting")

    node_rows = await _load_nodes(session)
    edge_rows = await _load_edges(session)

    graph: nx.MultiDiGraph = nx.MultiDiGraph()

    known_node_ids: set[uuid.UUID] = set()
    for node_id, osm_node_id, source, lon, lat in node_rows:
        known_node_ids.add(node_id)
        graph.add_node(
            node_id,
            intersection_id=node_id,
            osm_node_id=osm_node_id,
            source=source,
            x=float(lon),
            y=float(lat),
        )

    for (
        segment_id,
        road_id,
        start_id,
        end_id,
        source,
        osm_way_id,
        way_seq,
        is_oneway,
        road_class,
        length_m,
        maxspeed_kph,
        lanes,
        access,
    ) in edge_rows:
        if start_id not in known_node_ids:
            raise ValueError(
                f"RoadSegment {segment_id} references unknown start_intersection_id {start_id}"
            )
        if end_id not in known_node_ids:
            raise ValueError(
                f"RoadSegment {segment_id} references unknown end_intersection_id {end_id}"
            )

        base_attrs = {
            "road_segment_id": segment_id,
            "road_id": road_id,
            "source": source,
            "osm_way_id": osm_way_id,
            "way_seq": way_seq,
            "is_oneway": is_oneway,
            "road_class": road_class,
            "length_m": length_m,
            "weight": length_m,
            "maxspeed_kph": maxspeed_kph,
            "lanes": lanes,
            "access": access,
        }

        graph.add_edge(start_id, end_id, key=segment_id, reversed=False, **base_attrs)

        if not is_oneway and start_id != end_id:
            # Bidirectional: the reverse direction is a second directed
            # edge derived from the SAME canonical segment - same key
            # (road_segment_id), so both trace back to one PostGIS row.
            # A self-loop (start == end) never needs a synthesized
            # "reverse" - it would be the identical (u, v, key) triple.
            graph.add_edge(end_id, start_id, key=segment_id, reversed=True, **base_attrs)

    stats = compute_stats(graph, canonical_segment_count=len(edge_rows))
    duration_s = time.monotonic() - started
    logger.info(
        "graph build finished",
        extra={**stats.as_dict(), "duration_s": round(duration_s, 3)},
    )

    return GraphBuildResult(graph=graph, stats=stats)
