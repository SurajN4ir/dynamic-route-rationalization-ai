"""Deterministic development/test fixture data for the transportation
domain foundation (TASK-201).

Everything created here is SYNTHETIC - a small fictional grid, not real
OSM/GTFS data for any actual place. Every identifier is prefixed `DEV_`
to make that unmistakable in the database and in API responses. Real data
ingestion is TASK-202's job (OSM) and later GTFS import work, not this
script.

Idempotent: safe to run multiple times against the same database - it
looks up existing rows by their natural/unique key before inserting.

Usage:
    uv run python -m app.db.seed          # from services/api
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date

from geoalchemy2.shape import from_shape
from shapely.geometry import LineString, Point
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import dispose_engine, get_session_factory
from app.models.calendar import ServiceCalendar
from app.models.road_network import Intersection, Road, RoadSegment
from app.models.route import Route, RouteStop
from app.models.stop import Stop
from app.models.vehicle import Vehicle, VehicleAssignment

logger = logging.getLogger(__name__)

# A small fictional 2x2 grid, roughly 100m apart - not a real place.
_GRID_ORIGIN = (77.5946, 12.9716)  # (lon, lat) - arbitrary, synthetic
_STEP = 0.001  # ~100m at this latitude


def _grid_point(col: int, row: int) -> Point:
    lon, lat = _GRID_ORIGIN
    return Point(lon + col * _STEP, lat + row * _STEP)


async def _get_or_create_intersection(
    session: AsyncSession, osm_node_id: int, col: int, row: int
) -> Intersection:
    existing = await session.scalar(
        select(Intersection).where(Intersection.osm_node_id == osm_node_id)
    )
    if existing:
        return existing
    intersection = Intersection(
        location=from_shape(_grid_point(col, row), srid=4326),
        source="manual",
        osm_node_id=osm_node_id,
    )
    session.add(intersection)
    await session.flush()
    return intersection


async def seed_dev_data(session: AsyncSession) -> None:
    """Create the DEV_ fixture network if it doesn't already exist."""
    existing_road = await session.scalar(select(Road).where(Road.name == "DEV_MAIN_ST"))
    if existing_road is not None:
        logger.info("Dev fixture data already present - skipping seed.")
        return

    logger.info("Seeding synthetic development fixture data (DEV_* identifiers).")

    # Intersections forming a small square grid, node ids in a reserved
    # fake OSM-id range (9_000_000_000+) so they can never collide with a
    # real OSM node id once TASK-202 ingests actual data.
    nw = await _get_or_create_intersection(session, 9_000_000_001, 0, 1)
    ne = await _get_or_create_intersection(session, 9_000_000_002, 1, 1)
    se = await _get_or_create_intersection(session, 9_000_000_003, 1, 0)
    sw = await _get_or_create_intersection(session, 9_000_000_004, 0, 0)

    road = Road(name="DEV_MAIN_ST", road_class="residential", source="manual")
    session.add(road)
    await session.flush()

    def _segment(
        start: Intersection, end: Intersection, osm_way_id: int, p1: Point, p2: Point
    ) -> RoadSegment:
        line = LineString([p1, p2])
        return RoadSegment(
            road_id=road.id,
            start_intersection_id=start.id,
            end_intersection_id=end.id,
            geometry=from_shape(line, srid=4326),
            length_m=line.length
            * 111_320,  # rough degrees->meters at the equator; synthetic data only
            is_oneway=False,
            road_class="residential",
            source="manual",
            osm_way_id=osm_way_id,
        )

    segments = [
        _segment(nw, ne, 9_100_000_001, _grid_point(0, 1), _grid_point(1, 1)),
        _segment(ne, se, 9_100_000_002, _grid_point(1, 1), _grid_point(1, 0)),
        _segment(se, sw, 9_100_000_003, _grid_point(1, 0), _grid_point(0, 0)),
    ]
    session.add_all(segments)

    # Stops along the route, sitting near (not exactly on) the road grid.
    stop_a = Stop(
        code="DEV_STOP_A",
        name="Dev Stop A",
        location=from_shape(_grid_point(0, 1), srid=4326),
        capacity_hint=40,
        source="manual",
    )
    stop_b = Stop(
        code="DEV_STOP_B",
        name="Dev Stop B",
        location=from_shape(_grid_point(1, 1), srid=4326),
        capacity_hint=40,
        source="manual",
    )
    stop_c = Stop(
        code="DEV_STOP_C",
        name="Dev Stop C",
        location=from_shape(_grid_point(1, 0), srid=4326),
        capacity_hint=40,
        source="manual",
    )
    session.add_all([stop_a, stop_b, stop_c])
    await session.flush()

    route = Route(
        code="DEV_ROUTE_1",
        name="Dev Route 1",
        geometry=from_shape(
            LineString([_grid_point(0, 1), _grid_point(1, 1), _grid_point(1, 0)]), srid=4326
        ),
        direction="outbound",
        source="manual",
    )
    session.add(route)
    await session.flush()

    session.add_all(
        [
            RouteStop(route_id=route.id, sequence=0, stop_id=stop_a.id, scheduled_offset_s=0),
            RouteStop(route_id=route.id, sequence=1, stop_id=stop_b.id, scheduled_offset_s=180),
            RouteStop(route_id=route.id, sequence=2, stop_id=stop_c.id, scheduled_offset_s=360),
        ]
    )

    vehicle = Vehicle(external_code="DEV_BUS_01", capacity=40, source="real", status="active")
    session.add(vehicle)
    await session.flush()

    calendar = ServiceCalendar(
        code="DEV_WEEKDAY",
        monday=True,
        tuesday=True,
        wednesday=True,
        thursday=True,
        friday=True,
        saturday=False,
        sunday=False,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    session.add(calendar)
    await session.flush()

    session.add(
        VehicleAssignment(
            vehicle_id=vehicle.id,
            route_id=route.id,
            service_calendar_id=calendar.id,
            valid_from=date(2026, 1, 1),
            status="active",
        )
    )

    await session.commit()
    logger.info("Dev fixture data seeded successfully.")


async def _main() -> None:
    logging.basicConfig(level=logging.INFO)
    session_factory = get_session_factory()
    async with session_factory() as session:
        await seed_dev_data(session)
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(_main())
