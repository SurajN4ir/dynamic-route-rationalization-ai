from __future__ import annotations

from pathlib import Path

import pytest

from app.ingestion.osm.errors import OSMParseError
from app.ingestion.osm.parser import parse_osm_xml

FIXTURE = Path(__file__).parent.parent / "fixtures" / "osm" / "sample_extract.osm"


def test_parses_all_nodes() -> None:
    nodes, _ways = parse_osm_xml(FIXTURE)

    assert len(nodes) == 7
    assert nodes[1].lat == pytest.approx(12.9700)
    assert nodes[1].lon == pytest.approx(77.5900)


def test_parses_all_ways_unfiltered() -> None:
    """Parsing returns every <way>, including ones normalization will
    later reject - filtering is normalize's job, not parse's."""
    _nodes, ways = parse_osm_xml(FIXTURE)

    way_ids = {w.id for w in ways}
    assert way_ids == {100, 200, 300, 400, 500, 700}


def test_way_tags_and_node_refs_captured() -> None:
    _nodes, ways = parse_osm_xml(FIXTURE)
    way_100 = next(w for w in ways if w.id == 100)

    assert way_100.node_ids == (1, 2, 3)
    assert way_100.tags["highway"] == "residential"
    assert way_100.tags["name"] == "Test Main Street"
    assert way_100.tags["maxspeed"] == "40"


def test_missing_file_raises_parse_error() -> None:
    with pytest.raises(OSMParseError):
        parse_osm_xml(Path("does/not/exist.osm"))


def test_malformed_xml_raises_parse_error(tmp_path: Path) -> None:
    bad_file = tmp_path / "bad.osm"
    bad_file.write_text("<osm><node id='1' lat='0' lon='0'></osm>")  # unclosed <node>

    with pytest.raises(OSMParseError):
        parse_osm_xml(bad_file)
