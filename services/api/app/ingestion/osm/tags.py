"""Controlled OSM tag policy - see docs/architecture/TASK202_DESIGN.md §3.

Explicit allow-list rather than importing every tag OSM ways can carry.
Unsupported/unknown tags are simply ignored (not an error); only the
tags named here have any effect on ingestion.
"""

from __future__ import annotations

import re

from app.ingestion.osm.types import Direction

# Public-road, motor-vehicle-traversable highway values - matches the
# common "drivable network" convention (e.g. what osmnx's default `drive`
# network type covers). Deliberately excludes footway/cycleway/path/steps/
# pedestrian/track/service/construction/proposed and anything not meant
# for buses. This is the "controlled supported-tag policy" TASK-202 §4
# requires - extend deliberately, not by accident.
SUPPORTED_HIGHWAY_VALUES = frozenset(
    {
        "motorway",
        "trunk",
        "primary",
        "secondary",
        "tertiary",
        "unclassified",
        "residential",
        "living_street",
        "motorway_link",
        "trunk_link",
        "primary_link",
        "secondary_link",
        "tertiary_link",
    }
)

_ONEWAY_FORWARD_VALUES = frozenset({"yes", "1", "true"})
_ONEWAY_BACKWARD_VALUES = frozenset({"-1", "reverse"})
# oneway=reversible / alternating (time-dependent lanes) are conservatively
# treated as unrestricted (Direction.BOTH) - see known limitations in
# docs/architecture/TASK202_DESIGN.md §7.

_MAXSPEED_RE = re.compile(r"^\s*(\d+)\s*(mph|kph|km/h)?\s*$", re.IGNORECASE)


def parse_direction(oneway_tag: str | None) -> Direction:
    if oneway_tag is None:
        return Direction.BOTH
    value = oneway_tag.strip().lower()
    if value in _ONEWAY_FORWARD_VALUES:
        return Direction.FORWARD
    if value in _ONEWAY_BACKWARD_VALUES:
        return Direction.BACKWARD
    return Direction.BOTH


def parse_maxspeed_kph(maxspeed_tag: str | None) -> int | None:
    """Parses OSM `maxspeed` values like "50", "50 kph", "30 mph". Returns
    None for anything else (e.g. "none", "walk", "signals") rather than
    failing ingestion over an unparseable speed value."""
    if maxspeed_tag is None:
        return None
    match = _MAXSPEED_RE.match(maxspeed_tag)
    if not match:
        return None
    value, unit = int(match.group(1)), (match.group(2) or "kph").lower()
    if unit == "mph":
        return round(value * 1.60934)
    return value


def parse_lanes(lanes_tag: str | None) -> int | None:
    if lanes_tag is None:
        return None
    try:
        value = int(lanes_tag.strip())
    except ValueError:
        return None
    return value if value > 0 else None
