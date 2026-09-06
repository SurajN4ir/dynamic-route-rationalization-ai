"""Validation + normalization stage: raw OSMWay -> NormalizedWay | Rejection.

Kept separate from parsing (syntax) and topology (splitting/intersection
derivation) - see docs/architecture/TASK202_DESIGN.md §9's pipeline shape.
"""

from __future__ import annotations

from app.ingestion.osm.tags import (
    SUPPORTED_HIGHWAY_VALUES,
    parse_direction,
    parse_lanes,
    parse_maxspeed_kph,
)
from app.ingestion.osm.types import NormalizedWay, OSMWay, Rejection, RejectionReason


def normalize_ways(
    ways: list[OSMWay], known_node_ids: set[int]
) -> tuple[list[NormalizedWay], list[Rejection]]:
    """Filters and normalizes raw ways. Deterministic: same input always
    produces the same output in the same order, with no side effects."""
    normalized: list[NormalizedWay] = []
    rejections: list[Rejection] = []
    seen_way_ids: set[int] = set()

    for way in ways:
        if way.id in seen_way_ids:
            rejections.append(
                Rejection(way.id, RejectionReason.DUPLICATE_WAY_ID, "duplicate way id in source")
            )
            continue
        seen_way_ids.add(way.id)

        highway = way.tags.get("highway")
        if highway is None:
            rejections.append(Rejection(way.id, RejectionReason.NO_HIGHWAY_TAG))
            continue
        if highway not in SUPPORTED_HIGHWAY_VALUES:
            rejections.append(Rejection(way.id, RejectionReason.UNSUPPORTED_HIGHWAY_VALUE, highway))
            continue

        if len(way.node_ids) < 2:
            rejections.append(
                Rejection(way.id, RejectionReason.TOO_FEW_NODES, f"{len(way.node_ids)} node(s)")
            )
            continue

        unresolved = [n for n in way.node_ids if n not in known_node_ids]
        if unresolved:
            rejections.append(
                Rejection(
                    way.id,
                    RejectionReason.UNRESOLVED_NODE_REFERENCE,
                    f"node id(s) {unresolved} not present in source",
                )
            )
            continue

        normalized.append(
            NormalizedWay(
                osm_way_id=way.id,
                node_ids=way.node_ids,
                name=way.tags.get("name"),
                road_class=highway,
                direction=parse_direction(way.tags.get("oneway")),
                maxspeed_kph=parse_maxspeed_kph(way.tags.get("maxspeed")),
                lanes=parse_lanes(way.tags.get("lanes")),
                access=way.tags.get("access"),
            )
        )

    return normalized, rejections
