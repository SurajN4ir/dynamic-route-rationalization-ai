from __future__ import annotations

from pathlib import Path

from app.ingestion.osm.normalize import normalize_ways
from app.ingestion.osm.parser import parse_osm_xml
from app.ingestion.osm.types import Direction, OSMWay, RejectionReason

FIXTURE = Path(__file__).parent.parent / "fixtures" / "osm" / "sample_extract.osm"


def _normalize_fixture():
    nodes, ways = parse_osm_xml(FIXTURE)
    return normalize_ways(ways, set(nodes.keys()))


def test_eligible_ways_are_the_supported_highway_ones() -> None:
    normalized, _rejections = _normalize_fixture()

    eligible_ids = {w.osm_way_id for w in normalized}
    assert eligible_ids == {100, 200, 700}


def test_rejects_unsupported_highway_value() -> None:
    _normalized, rejections = _normalize_fixture()

    rejection = next(r for r in rejections if r.way_id == 300)
    assert rejection.reason == RejectionReason.UNSUPPORTED_HIGHWAY_VALUE
    assert rejection.detail == "footway"


def test_rejects_way_with_too_few_nodes() -> None:
    _normalized, rejections = _normalize_fixture()

    rejection = next(r for r in rejections if r.way_id == 400)
    assert rejection.reason == RejectionReason.TOO_FEW_NODES


def test_rejects_way_with_unresolved_node_reference() -> None:
    _normalized, rejections = _normalize_fixture()

    rejection = next(r for r in rejections if r.way_id == 500)
    assert rejection.reason == RejectionReason.UNRESOLVED_NODE_REFERENCE


def test_rejection_count_matches_unsupported_ways() -> None:
    _normalized, rejections = _normalize_fixture()

    assert len(rejections) == 3  # ways 300, 400, 500


def test_way_without_highway_tag_is_rejected() -> None:
    normalized, rejections = normalize_ways(
        [OSMWay(id=1, node_ids=(1, 2), tags={"name": "no highway tag"})],
        known_node_ids={1, 2},
    )

    assert normalized == []
    assert rejections[0].reason == RejectionReason.NO_HIGHWAY_TAG


def test_duplicate_way_id_in_source_is_rejected() -> None:
    ways = [
        OSMWay(id=1, node_ids=(1, 2), tags={"highway": "residential"}),
        OSMWay(id=1, node_ids=(3, 4), tags={"highway": "residential"}),
    ]

    normalized, rejections = normalize_ways(ways, known_node_ids={1, 2, 3, 4})

    assert len(normalized) == 1
    assert rejections[0].reason == RejectionReason.DUPLICATE_WAY_ID


def test_normalized_way_direction_and_tags() -> None:
    normalized, _rejections = _normalize_fixture()

    way_100 = next(w for w in normalized if w.osm_way_id == 100)
    assert way_100.direction == Direction.BOTH
    assert way_100.name == "Test Main Street"
    assert way_100.maxspeed_kph == 40
    assert way_100.lanes == 2

    way_200 = next(w for w in normalized if w.osm_way_id == 200)
    assert way_200.direction == Direction.FORWARD

    way_700 = next(w for w in normalized if w.osm_way_id == 700)
    assert way_700.direction == Direction.BACKWARD


def test_way_with_no_name_tag_normalizes_to_none() -> None:
    normalized, _ = normalize_ways(
        [OSMWay(id=9, node_ids=(1, 2), tags={"highway": "residential"})],
        known_node_ids={1, 2},
    )

    assert normalized[0].name is None
