"""Builds and validates segment geometry from OSM node coordinates - see
docs/architecture/TASK202_DESIGN.md §8.

Geometry is validated *before* it ever reaches a database write: a
malformed candidate (degenerate to a single point, or otherwise invalid
per OGC simple-features rules) is rejected deterministically here rather
than being silently inserted or causing PostGIS to reject the whole
transaction with an opaque error later.
"""

from __future__ import annotations

from shapely.geometry import LineString

from app.ingestion.osm.types import OSMNode, SegmentCandidate

# Rough conversion good enough for a cached display/estimate field, not
# for anything routing-precision-sensitive (doc TASK-202 §16: this is a
# deliberate simplification, not a geodesic length calculation).
_DEGREES_TO_METERS_AT_EQUATOR = 111_320


def build_linestring(segment: SegmentCandidate, nodes_by_id: dict[int, OSMNode]) -> LineString:
    coords = [(nodes_by_id[n].lon, nodes_by_id[n].lat) for n in segment.node_ids]
    return LineString(coords)


def is_valid_segment_geometry(line: LineString) -> bool:
    if not line.is_valid:
        return False
    if line.length == 0:
        # every coordinate identical - a degenerate, zero-length segment
        return False
    return len(set(line.coords)) >= 2


def estimate_length_m(line: LineString) -> float:
    return line.length * _DEGREES_TO_METERS_AT_EQUATOR
