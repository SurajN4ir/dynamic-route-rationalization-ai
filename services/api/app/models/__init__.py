"""Domain models package.

Importing this module registers every table on `app.db.base.Base.metadata`
- required so Alembic (and anything introspecting the metadata) sees the
full schema. Add new model modules here as they're created; don't rely on
import side effects from elsewhere.
"""

from app.models.calendar import ServiceCalendar
from app.models.road_network import Intersection, Road, RoadSegment
from app.models.route import Route, RouteStop
from app.models.stop import Stop
from app.models.telemetry import Telemetry
from app.models.vehicle import Vehicle, VehicleAssignment

__all__ = [
    "Intersection",
    "Road",
    "RoadSegment",
    "Route",
    "RouteStop",
    "ServiceCalendar",
    "Stop",
    "Telemetry",
    "Vehicle",
    "VehicleAssignment",
]
