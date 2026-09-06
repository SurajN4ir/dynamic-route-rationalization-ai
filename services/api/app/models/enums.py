"""Python-side enums for status/source columns.

The database stores these as `text` with a `CHECK` constraint (matching
the convention already established in docs/architecture/04-data-model.md
for `vehicles.status`/`source`, etc.) rather than a native Postgres ENUM
type - text+CHECK is cheaper to extend later (adding a value is a
constraint migration, not a type migration) and matches what's already
committed. These enums exist purely so application/API code doesn't pass
magic strings around.
"""

from __future__ import annotations

from enum import StrEnum


class DataSource(StrEnum):
    """Where a transportation record originated. Used by Intersection,
    Road, RoadSegment, Stop, and Route - the entities TASK-202's OSM
    ingestion will populate."""

    OSM = "osm"
    GTFS = "gtfs"
    MANUAL = "manual"


class VehicleSource(StrEnum):
    REAL = "real"
    SIMULATED = "simulated"


class VehicleStatus(StrEnum):
    ACTIVE = "active"
    SPARE = "spare"
    MAINTENANCE = "maintenance"


class VehicleAssignmentStatus(StrEnum):
    ACTIVE = "active"
    ENDED = "ended"
