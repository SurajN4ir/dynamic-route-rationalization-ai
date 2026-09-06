"""Factory helpers for building minimal, clearly-synthetic transportation
domain objects in tests. Every value defaults to something obviously fake
(TEST_ prefixes, null-island-adjacent coordinates) - callers override only
what the test cares about.
"""

from __future__ import annotations

import uuid
from datetime import date

from geoalchemy2.shape import from_shape
from shapely.geometry import LineString, Point
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.calendar import ServiceCalendar
from app.models.road_network import Intersection, Road, RoadSegment
from app.models.route import Route, RouteStop
from app.models.stop import Stop
from app.models.vehicle import Vehicle, VehicleAssignment


def _unique(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def make_intersection(lon: float = 10.0, lat: float = 10.0, **kwargs: object) -> Intersection:
    return Intersection(location=from_shape(Point(lon, lat), srid=4326), **kwargs)  # type: ignore[arg-type]


def make_road(**kwargs: object) -> Road:
    kwargs.setdefault("name", _unique("TEST_ROAD"))
    return Road(**kwargs)  # type: ignore[arg-type]


def make_road_segment(
    start: Intersection, end: Intersection, p1: Point, p2: Point, **kwargs: object
) -> RoadSegment:
    return RoadSegment(
        start_intersection_id=start.id,
        end_intersection_id=end.id,
        geometry=from_shape(LineString([p1, p2]), srid=4326),
        **kwargs,  # type: ignore[arg-type]
    )


def make_stop(lon: float = 10.0, lat: float = 10.0, **kwargs: object) -> Stop:
    kwargs.setdefault("code", _unique("TEST_STOP"))
    return Stop(location=from_shape(Point(lon, lat), srid=4326), **kwargs)  # type: ignore[arg-type]


def make_route(**kwargs: object) -> Route:
    kwargs.setdefault("code", _unique("TEST_ROUTE"))
    return Route(**kwargs)  # type: ignore[arg-type]


def make_route_stop(route: Route, sequence: int, stop: Stop, **kwargs: object) -> RouteStop:
    return RouteStop(route_id=route.id, sequence=sequence, stop_id=stop.id, **kwargs)  # type: ignore[arg-type]


def make_vehicle(**kwargs: object) -> Vehicle:
    kwargs.setdefault("external_code", _unique("TEST_VEHICLE"))
    return Vehicle(**kwargs)  # type: ignore[arg-type]


def make_service_calendar(**kwargs: object) -> ServiceCalendar:
    kwargs.setdefault("code", _unique("TEST_CALENDAR"))
    kwargs.setdefault("start_date", date(2026, 1, 1))
    kwargs.setdefault("end_date", date(2026, 12, 31))
    return ServiceCalendar(**kwargs)  # type: ignore[arg-type]


def make_vehicle_assignment(
    vehicle: Vehicle, route: Route, calendar: ServiceCalendar, **kwargs: object
) -> VehicleAssignment:
    kwargs.setdefault("valid_from", date(2026, 1, 1))
    return VehicleAssignment(
        vehicle_id=vehicle.id,
        route_id=route.id,
        service_calendar_id=calendar.id,
        **kwargs,  # type: ignore[arg-type]
    )


async def flush(session: AsyncSession, *objects: object) -> None:
    session.add_all(objects)
    await session.flush()
