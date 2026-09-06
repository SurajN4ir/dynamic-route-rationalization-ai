"""Data-integrity tests for the Phase 2 transportation schema - the
"do not weaken tests" constraints explicitly called out in TASK-201:
RouteStop sequence ordering/uniqueness, valid FK relationships, vehicle
assignment consistency, road segment topology, and idempotent source
identifiers.

Every test runs against the real PostGIS database (see
tests/integration/conftest.py) inside a rolled-back transaction, so a
constraint violation is exercised for real, not simulated.
"""

from __future__ import annotations

from datetime import date

import pytest
from shapely.geometry import Point
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.route import RouteStop
from tests.fixtures.transportation import (
    flush,
    make_intersection,
    make_road_segment,
    make_route,
    make_route_stop,
    make_service_calendar,
    make_stop,
    make_vehicle,
    make_vehicle_assignment,
)


async def test_route_stop_rejects_duplicate_sequence_on_same_route(
    db_session: AsyncSession,
) -> None:
    """The exact rule doc 04 / the Phase 0 review fixed: sequence alone
    determines position, so two different stops can't share a sequence
    number on the same route."""
    route = make_route()
    stop_a = make_stop(10.0, 10.0)
    stop_b = make_stop(10.001, 10.001)
    await flush(db_session, route, stop_a, stop_b)

    db_session.add(make_route_stop(route, 0, stop_a))
    await db_session.flush()

    db_session.add(make_route_stop(route, 0, stop_b))  # same sequence, different stop
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_route_stop_allows_same_stop_at_different_sequences(
    db_session: AsyncSession,
) -> None:
    """A loop route may legitimately revisit the same stop - doc 04
    explicitly notes stop_id is not unique in route_stops."""
    route = make_route()
    stop = make_stop()
    await flush(db_session, route, stop)

    db_session.add(make_route_stop(route, 0, stop))
    db_session.add(make_route_stop(route, 5, stop))
    await db_session.flush()  # must not raise

    result = await db_session.execute(
        RouteStop.__table__.select().where(RouteStop.route_id == route.id)
    )
    assert len(result.fetchall()) == 2


async def test_route_stop_rejects_negative_sequence(db_session: AsyncSession) -> None:
    route = make_route()
    stop = make_stop()
    await flush(db_session, route, stop)

    db_session.add(make_route_stop(route, -1, stop))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_route_stop_rejects_unknown_stop(db_session: AsyncSession) -> None:
    """A route_stop must reference a real stop - FK enforcement."""
    import uuid

    route = make_route()
    await flush(db_session, route)

    db_session.add(RouteStop(route_id=route.id, sequence=0, stop_id=uuid.uuid4()))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_deleting_route_cascades_to_route_stops(db_session: AsyncSession) -> None:
    route = make_route()
    stop = make_stop()
    await flush(db_session, route, stop)
    db_session.add(make_route_stop(route, 0, stop))
    await db_session.flush()

    await db_session.delete(route)
    await db_session.flush()  # must not raise (route_stops FK is ON DELETE CASCADE)


async def test_deleting_stop_referenced_by_route_stop_is_restricted(
    db_session: AsyncSession,
) -> None:
    route = make_route()
    stop = make_stop()
    await flush(db_session, route, stop)
    db_session.add(make_route_stop(route, 0, stop))
    await db_session.flush()

    await db_session.delete(stop)
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_stop_code_must_be_unique(db_session: AsyncSession) -> None:
    stop1 = make_stop(code="TEST_DUP_CODE")
    await flush(db_session, stop1)

    db_session.add(make_stop(code="TEST_DUP_CODE"))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_stop_source_check_constraint_rejects_invalid_value(
    db_session: AsyncSession,
) -> None:
    db_session.add(make_stop(source="not_a_real_source"))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_stop_source_id_unique_only_when_present(db_session: AsyncSession) -> None:
    """Two manually-created stops with no source_id must not conflict
    (NULL <> NULL); two stops claiming the same (source, source_id) must."""
    await flush(db_session, make_stop(source="manual"), make_stop(source="manual"))  # no raise

    db_session.add(make_stop(source="osm", source_id="way/123"))
    await db_session.flush()
    db_session.add(make_stop(source="osm", source_id="way/123"))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_vehicle_status_check_constraint(db_session: AsyncSession) -> None:
    db_session.add(make_vehicle(status="on_fire"))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_road_segment_requires_valid_intersections(db_session: AsyncSession) -> None:
    import uuid

    from geoalchemy2.shape import from_shape
    from shapely.geometry import LineString

    from app.models.road_network import RoadSegment

    db_session.add(
        RoadSegment(
            start_intersection_id=uuid.uuid4(),
            end_intersection_id=uuid.uuid4(),
            geometry=from_shape(LineString([Point(0, 0), Point(1, 1)]), srid=4326),
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_road_segment_osm_way_id_unique_when_present(db_session: AsyncSession) -> None:
    i1 = make_intersection(0.0, 0.0)
    i2 = make_intersection(0.001, 0.001)
    i3 = make_intersection(0.002, 0.002)
    await flush(db_session, i1, i2, i3)

    seg1 = make_road_segment(i1, i2, Point(0, 0), Point(0.001, 0.001), osm_way_id=555)
    await flush(db_session, seg1)

    seg2 = make_road_segment(i2, i3, Point(0.001, 0.001), Point(0.002, 0.002), osm_way_id=555)
    db_session.add(seg2)
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_vehicle_assignment_rejects_invalid_date_range(db_session: AsyncSession) -> None:
    vehicle = make_vehicle()
    route = make_route()
    calendar = make_service_calendar()
    await flush(db_session, vehicle, route, calendar)

    db_session.add(
        make_vehicle_assignment(
            vehicle, route, calendar, valid_from=date(2026, 6, 1), valid_to=date(2026, 1, 1)
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_vehicle_assignment_rejects_duplicate_natural_key(db_session: AsyncSession) -> None:
    vehicle = make_vehicle()
    route = make_route()
    calendar = make_service_calendar()
    await flush(db_session, vehicle, route, calendar)

    await flush(db_session, make_vehicle_assignment(vehicle, route, calendar))
    db_session.add(make_vehicle_assignment(vehicle, route, calendar))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_service_calendar_rejects_end_before_start(db_session: AsyncSession) -> None:
    db_session.add(make_service_calendar(start_date=date(2026, 6, 1), end_date=date(2026, 1, 1)))
    with pytest.raises(IntegrityError):
        await db_session.flush()
