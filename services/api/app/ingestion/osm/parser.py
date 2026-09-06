"""Parses OSM XML (`.osm`) into intermediate OSMNode/OSMWay records.

Uses the standard library's `xml.etree.ElementTree` rather than a new
dependency (e.g. osmium/pyosmium for `.osm.pbf`) - see
docs/architecture/TASK202_DESIGN.md §3/§21 for why `.osm.pbf` support is
deliberately deferred. `ElementTree.iterparse` is used so a larger extract
doesn't have to be held as a DOM tree in memory (doc TASK-202 §16
performance guidance).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from xml.etree.ElementTree import iterparse

from app.ingestion.osm.errors import OSMParseError
from app.ingestion.osm.types import OSMNode, OSMWay


def parse_osm_xml(path: Path) -> tuple[dict[int, OSMNode], list[OSMWay]]:
    """Returns (nodes_by_id, ways) for the given `.osm` XML file.

    Every <way> is returned, unfiltered - highway-tag eligibility and
    node-reference validity are the normalization stage's job (parsing
    stays a pure syntactic concern).
    """
    nodes: dict[int, OSMNode] = {}
    ways: list[OSMWay] = []

    try:
        events = iterparse(str(path), events=("start", "end"))
        current_way_id: int | None = None
        current_way_nodes: list[int] = []
        current_way_tags: dict[str, str] = {}

        for event, elem in events:
            if event == "start" and elem.tag == "node":
                node_id = elem.get("id")
                lat = elem.get("lat")
                lon = elem.get("lon")
                if node_id is None or lat is None or lon is None:
                    raise OSMParseError(f"<node> missing id/lat/lon: {elem.attrib}")
                nodes[int(node_id)] = OSMNode(id=int(node_id), lat=float(lat), lon=float(lon))

            elif event == "start" and elem.tag == "way":
                way_id = elem.get("id")
                if way_id is None:
                    raise OSMParseError(f"<way> missing id: {elem.attrib}")
                current_way_id = int(way_id)
                current_way_nodes = []
                current_way_tags = {}

            elif event == "start" and elem.tag == "nd" and current_way_id is not None:
                ref = elem.get("ref")
                if ref is None:
                    raise OSMParseError(f"<nd> missing ref in way {current_way_id}")
                current_way_nodes.append(int(ref))

            elif event == "start" and elem.tag == "tag" and current_way_id is not None:
                key, value = elem.get("k"), elem.get("v")
                if key is not None and value is not None:
                    current_way_tags[key] = value

            elif event == "end" and elem.tag == "way" and current_way_id is not None:
                ways.append(
                    OSMWay(
                        id=current_way_id,
                        node_ids=tuple(current_way_nodes),
                        tags=current_way_tags,
                    )
                )
                current_way_id = None

            # Free the element once we're done with it - keeps peak memory
            # bounded regardless of file size (doc TASK-202 §16).
            if event == "end" and elem.tag in ("node", "way"):
                elem.clear()

    except OSMParseError:
        raise
    except Exception as exc:  # malformed XML, encoding errors, etc.
        raise OSMParseError(f"failed to parse {path}: {exc}") from exc

    return nodes, ways


def iter_way_node_ids(ways: list[OSMWay]) -> Iterator[tuple[int, tuple[int, ...]]]:
    for way in ways:
        yield way.id, way.node_ids
