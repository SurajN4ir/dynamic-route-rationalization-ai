"""Intersection derivation + way splitting - see
docs/architecture/TASK202_DESIGN.md §6/§7.

A node qualifies as a canonical Intersection if it is:
  (a) the first or last node of at least one eligible way (every
      RoadSegment needs an endpoint even at a dead end), or
  (b) referenced by two or more *distinct* eligible ways (a real
      topological junction).
Nodes that only appear as an interior "shape point" of a single way do
not become Intersections - they just shape that way's segment geometry.

Each way is then split into one SegmentCandidate per consecutive pair of
intersection nodes along its node list - this is what makes a single OSM
way become multiple RoadSegment rows when it passes through a junction
partway along its length (docs/architecture/TASK202_DESIGN.md §1/§5).
"""

from __future__ import annotations

from app.ingestion.osm.types import Direction, NormalizedWay, SegmentCandidate


def compute_intersection_node_ids(ways: list[NormalizedWay]) -> set[int]:
    node_way_ids: dict[int, set[int]] = {}
    endpoints: set[int] = set()

    for way in ways:
        endpoints.add(way.node_ids[0])
        endpoints.add(way.node_ids[-1])
        for node_id in set(way.node_ids):  # set() - a way touching a node
            # twice (e.g. a small loop) counts as one reference, not two
            node_way_ids.setdefault(node_id, set()).add(way.osm_way_id)

    junctions = {node_id for node_id, way_ids in node_way_ids.items() if len(way_ids) >= 2}
    return endpoints | junctions


def split_way_into_segments(
    way: NormalizedWay, intersection_node_ids: set[int]
) -> list[SegmentCandidate]:
    """Splits one way at every intersection node it passes through.
    Deterministic and order-preserving: re-running on the same way and
    the same intersection set always yields the same `way_seq` sequence.
    """
    split_indices = [
        i for i, node_id in enumerate(way.node_ids) if node_id in intersection_node_ids
    ]
    # way.node_ids[0] and [-1] are always intersection nodes (endpoints,
    # per compute_intersection_node_ids), so split_indices always starts
    # at 0 and ends at len - 1.

    segments: list[SegmentCandidate] = []
    for way_seq, (start_idx, end_idx) in enumerate(
        zip(split_indices, split_indices[1:], strict=False)
    ):
        sub_path = way.node_ids[start_idx : end_idx + 1]
        if way.direction == Direction.BACKWARD:
            sub_path = tuple(reversed(sub_path))

        segments.append(
            SegmentCandidate(
                osm_way_id=way.osm_way_id,
                way_seq=way_seq,
                start_node_id=sub_path[0],
                end_node_id=sub_path[-1],
                node_ids=sub_path,
                name=way.name,
                road_class=way.road_class,
                is_oneway=way.direction != Direction.BOTH,
                maxspeed_kph=way.maxspeed_kph,
                lanes=way.lanes,
                access=way.access,
            )
        )

    return segments
