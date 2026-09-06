"""Graph node/edge attribute schema - see
docs/architecture/TASK203_DESIGN.md §2/§3/§4.

Deliberately plain TypedDicts, not a new ORM-adjacent model layer: the
graph is derived, in-memory, disposable data (docs/architecture/
PHASE2_DESIGN.md's "PostGIS is the system of record" principle) - these
exist only to document and type-check what a node/edge attribute dict
actually contains, not to be persisted anywhere.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    import networkx as nx

    from app.graph.stats import GraphStats


class NodeAttrs(TypedDict):
    """One graph node = one canonical Intersection. `x`/`y` (lon/lat) are
    copied out of PostGIS as plain floats - the standard NetworkX/OSMnx
    node-coordinate convention - for computational convenience (any graph
    algorithm needs coordinates without a DB round trip). This is derived,
    read-only convenience data, not a second authoritative geometry store;
    the canonical geometry stays in `intersections.location`."""

    intersection_id: uuid.UUID
    osm_node_id: int | None
    source: str
    x: float  # longitude
    y: float  # latitude


class EdgeAttrs(TypedDict):
    """One directed graph edge = one traversal direction of one canonical
    RoadSegment. A bidirectional segment produces two EdgeAttrs dicts
    (one per direction, see docs/architecture/TASK203_DESIGN.md §5); both
    carry the *same* `road_segment_id` - that field, not the (u, v) pair,
    is the mandatory traceability link back to PostGIS. Geometry itself is
    deliberately NOT copied here (§8 of the design doc) - a consumer that
    needs it queries `road_segments.geometry` by `road_segment_id`.
    """

    road_segment_id: uuid.UUID
    road_id: uuid.UUID | None
    source: str
    osm_way_id: int | None
    way_seq: int | None
    is_oneway: bool
    reversed: bool  # True for the synthesized B->A edge of a bidirectional segment
    road_class: str | None
    length_m: float | None
    weight: float | None  # alias of length_m, the NetworkX-conventional attribute name
    maxspeed_kph: int | None
    lanes: int | None
    access: str | None


@dataclass(frozen=True, slots=True)
class GraphBuildResult:
    graph: nx.MultiDiGraph
    stats: GraphStats
