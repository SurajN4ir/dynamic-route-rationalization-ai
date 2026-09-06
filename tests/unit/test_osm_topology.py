from __future__ import annotations

from pathlib import Path

from app.ingestion.osm.normalize import normalize_ways
from app.ingestion.osm.parser import parse_osm_xml
from app.ingestion.osm.topology import compute_intersection_node_ids, split_way_into_segments
from app.ingestion.osm.types import Direction, NormalizedWay

FIXTURE = Path(__file__).parent.parent / "fixtures" / "osm" / "sample_extract.osm"


def _normalized_fixture_ways() -> list[NormalizedWay]:
    nodes, ways = parse_osm_xml(FIXTURE)
    normalized, _rejections = normalize_ways(ways, set(nodes.keys()))
    return normalized


def test_shared_node_is_detected_as_intersection() -> None:
    """Node 2 is the last node of way 100 AND the first node of way 200 -
    a real topological junction, not just a shape point."""
    ways = _normalized_fixture_ways()

    intersections = compute_intersection_node_ids(ways)

    assert 2 in intersections


def test_dead_end_nodes_are_intersections_too() -> None:
    """Every way endpoint qualifies, even with no other way touching it -
    a RoadSegment always needs a start/end Intersection."""
    ways = _normalized_fixture_ways()

    intersections = compute_intersection_node_ids(ways)

    assert {1, 3, 4, 6, 7} <= intersections


def test_way_100_splits_at_the_shared_node() -> None:
    ways = _normalized_fixture_ways()
    way_100 = next(w for w in ways if w.osm_way_id == 100)
    intersections = compute_intersection_node_ids(ways)

    segments = split_way_into_segments(way_100, intersections)

    assert len(segments) == 2
    assert segments[0].way_seq == 0
    assert (segments[0].start_node_id, segments[0].end_node_id) == (1, 2)
    assert segments[1].way_seq == 1
    assert (segments[1].start_node_id, segments[1].end_node_id) == (2, 3)


def test_way_200_does_not_split_and_is_forward_oneway() -> None:
    ways = _normalized_fixture_ways()
    way_200 = next(w for w in ways if w.osm_way_id == 200)
    intersections = compute_intersection_node_ids(ways)

    segments = split_way_into_segments(way_200, intersections)

    assert len(segments) == 1
    assert (segments[0].start_node_id, segments[0].end_node_id) == (2, 4)
    assert segments[0].is_oneway is True


def test_way_700_reverses_direction_for_oneway_minus_one() -> None:
    """oneway=-1 on nodes [6, 7] means the allowed travel direction is
    7 -> 6, the reverse of the way's own node order."""
    ways = _normalized_fixture_ways()
    way_700 = next(w for w in ways if w.osm_way_id == 700)
    intersections = compute_intersection_node_ids(ways)

    segments = split_way_into_segments(way_700, intersections)

    assert len(segments) == 1
    assert (segments[0].start_node_id, segments[0].end_node_id) == (7, 6)
    assert segments[0].node_ids == (7, 6)
    assert segments[0].is_oneway is True


def test_bidirectional_way_segment_is_not_marked_oneway() -> None:
    ways = _normalized_fixture_ways()
    way_100 = next(w for w in ways if w.osm_way_id == 100)
    intersections = compute_intersection_node_ids(ways)

    segments = split_way_into_segments(way_100, intersections)

    assert all(not s.is_oneway for s in segments)


def test_way_with_only_shape_points_does_not_split() -> None:
    """A node referenced by only one way, and not that way's endpoint, is
    a shape point, not an intersection - the way must not split there."""
    way = NormalizedWay(
        osm_way_id=1,
        node_ids=(10, 11, 12, 13),
        name=None,
        road_class="residential",
        direction=Direction.BOTH,
        maxspeed_kph=None,
        lanes=None,
        access=None,
    )
    intersections = compute_intersection_node_ids([way])

    segments = split_way_into_segments(way, intersections)

    assert intersections == {10, 13}
    assert len(segments) == 1
    assert segments[0].node_ids == (10, 11, 12, 13)
