from __future__ import annotations

from app.ingestion.osm.geometry import (
    build_linestring,
    estimate_length_m,
    is_valid_segment_geometry,
)
from app.ingestion.osm.types import OSMNode, SegmentCandidate


def _candidate(node_ids: tuple[int, ...]) -> SegmentCandidate:
    return SegmentCandidate(
        osm_way_id=1,
        way_seq=0,
        start_node_id=node_ids[0],
        end_node_id=node_ids[-1],
        node_ids=node_ids,
        name=None,
        road_class="residential",
        is_oneway=False,
        maxspeed_kph=None,
        lanes=None,
        access=None,
    )


def test_build_linestring_uses_lon_lat_order() -> None:
    nodes = {1: OSMNode(1, lat=10.0, lon=20.0), 2: OSMNode(2, lat=11.0, lon=21.0)}

    line = build_linestring(_candidate((1, 2)), nodes)

    assert list(line.coords) == [(20.0, 10.0), (21.0, 11.0)]


def test_valid_two_point_segment() -> None:
    nodes = {1: OSMNode(1, lat=10.0, lon=20.0), 2: OSMNode(2, lat=10.001, lon=20.001)}

    line = build_linestring(_candidate((1, 2)), nodes)

    assert is_valid_segment_geometry(line) is True


def test_degenerate_zero_length_segment_is_invalid() -> None:
    """Both nodes at the exact same coordinate - a real (if unusual) case
    for a malformed/duplicated OSM node reference."""
    nodes = {1: OSMNode(1, lat=10.0, lon=20.0), 2: OSMNode(2, lat=10.0, lon=20.0)}

    line = build_linestring(_candidate((1, 2)), nodes)

    assert is_valid_segment_geometry(line) is False


def test_estimate_length_is_positive_for_a_real_segment() -> None:
    nodes = {1: OSMNode(1, lat=10.0, lon=20.0), 2: OSMNode(2, lat=10.001, lon=20.001)}

    line = build_linestring(_candidate((1, 2)), nodes)

    assert estimate_length_m(line) > 0
