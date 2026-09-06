"""Intermediate (parsed-but-not-yet-canonical) OSM representations.

Deliberately separate from app.models - these carry raw OSM fields
(node id lists, tag dicts) that have no place in the canonical schema.
Parsing produces these; normalization consumes them and produces
canonical-shaped values; nothing in this module ever touches the database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class OSMNode:
    id: int
    lat: float
    lon: float


@dataclass(frozen=True, slots=True)
class OSMWay:
    id: int
    node_ids: tuple[int, ...]
    tags: dict[str, str] = field(default_factory=dict)


class RejectionReason(StrEnum):
    NO_HIGHWAY_TAG = "no_highway_tag"
    UNSUPPORTED_HIGHWAY_VALUE = "unsupported_highway_value"
    TOO_FEW_NODES = "too_few_nodes"
    UNRESOLVED_NODE_REFERENCE = "unresolved_node_reference"
    DUPLICATE_WAY_ID = "duplicate_way_id"
    INVALID_GEOMETRY = "invalid_geometry"


@dataclass(frozen=True, slots=True)
class Rejection:
    way_id: int
    reason: RejectionReason
    detail: str = ""


class Direction(StrEnum):
    """Normalized OSM `oneway` semantics - see
    docs/architecture/TASK202_DESIGN.md §7."""

    FORWARD = "forward"  # travel only in the way's node order
    BACKWARD = "backward"  # travel only against the way's node order (oneway=-1)
    BOTH = "both"  # bidirectional (no oneway tag, oneway=no, or a
    # time-dependent value like "reversible"/"alternating" -
    # conservatively treated as unrestricted; see known limitations)


@dataclass(frozen=True, slots=True)
class NormalizedWay:
    """A single eligible OSM way after tag normalization, before
    topology/splitting is applied."""

    osm_way_id: int
    node_ids: tuple[int, ...]
    name: str | None
    road_class: str
    direction: Direction
    maxspeed_kph: int | None
    lanes: int | None
    access: str | None


@dataclass(frozen=True, slots=True)
class SegmentCandidate:
    """One canonical RoadSegment-to-be, after way splitting. `way_seq` is
    this candidate's 0-based split index within its parent way."""

    osm_way_id: int
    way_seq: int
    start_node_id: int
    end_node_id: int
    node_ids: tuple[int, ...]  # full path incl. endpoints, for geometry
    name: str | None
    road_class: str
    is_oneway: bool
    maxspeed_kph: int | None
    lanes: int | None
    access: str | None
