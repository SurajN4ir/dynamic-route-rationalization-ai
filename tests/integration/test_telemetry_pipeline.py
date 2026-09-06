"""Integration tests for app.telemetry.pipeline.ingest_telemetry and
app.telemetry.state.get_vehicle_state against real PostGIS + Redis (see
tests/integration/conftest.py) - persistence, idempotency, ordering,
segment association, and current-state retrieval.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import redis.asyncio as redis_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.telemetry import Telemetry
from app.telemetry.pipeline import TelemetryRejected, UnknownVehicleError, ingest_telemetry
from app.telemetry.state import get_vehicle_state
from tests.fixtures.telemetry import make_telemetry_event
from tests.fixtures.transportation import (
    flush,
    make_intersection,
    make_road_segment,
    make_route,
    make_service_calendar,
    make_vehicle,
    make_vehicle_assignment,
)

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

_PIPELINE_KWARGS: dict[str, Any] = {
    "max_speed_mps": 40.0,
    "max_clock_skew_past_s": 30,
    "max_clock_skew_future_s": 5,
    "segment_search_radius_m": 50.0,
    "state_cache_ttl_s": 1800,
}


async def _ingest(session, redis_client, payload, *, now: datetime = T0):
    return await ingest_telemetry(session, redis_client, payload, now=now, **_PIPELINE_KWARGS)


async def _count_rows(session: AsyncSession, vehicle_id) -> int:
    result = await session.execute(select(Telemetry).where(Telemetry.vehicle_id == vehicle_id))
    return len(result.scalars().all())


async def test_valid_telemetry_is_persisted_and_advances_state(
    db_session: AsyncSession, redis_client: redis_asyncio.Redis
) -> None:
    vehicle = make_vehicle()
    await flush(db_session, vehicle)
    payload = make_telemetry_event(vehicle.id, lat=10.0, lon=10.0, ts=T0)

    result = await _ingest(db_session, redis_client, payload)

    assert result.status == "accepted"
    assert result.state_updated is True
    assert result.telemetry_id is not None
    assert await _count_rows(db_session, vehicle.id) == 1


async def test_duplicate_event_is_recognized_and_not_double_persisted(
    db_session: AsyncSession, redis_client: redis_asyncio.Redis
) -> None:
    vehicle = make_vehicle()
    await flush(db_session, vehicle)
    payload = make_telemetry_event(vehicle.id, ts=T0)

    first = await _ingest(db_session, redis_client, payload)
    second = await _ingest(db_session, redis_client, payload)

    assert first.status == "accepted"
    assert second.status == "duplicate"
    assert second.state_updated is False
    assert await _count_rows(db_session, vehicle.id) == 1


async def test_out_of_order_event_is_recorded_but_does_not_regress_state(
    db_session: AsyncSession, redis_client: redis_asyncio.Redis
) -> None:
    """The exact TASK-204 §4 scenario: 14:00:12 arrives, then a
    14:00:11 sample arrives late. History gets both rows; current state
    stays at 14:00:12."""
    vehicle = make_vehicle()
    await flush(db_session, vehicle)
    newer = make_telemetry_event(vehicle.id, lat=11.0, ts=T0 + timedelta(seconds=2))
    older = make_telemetry_event(vehicle.id, lat=12.0, ts=T0 + timedelta(seconds=1))

    newer_result = await _ingest(db_session, redis_client, newer, now=T0 + timedelta(seconds=2))
    older_result = await _ingest(db_session, redis_client, older, now=T0 + timedelta(seconds=2))

    assert newer_result.state_updated is True
    assert older_result.status == "accepted"
    assert older_result.state_updated is False
    assert await _count_rows(db_session, vehicle.id) == 2

    state = await get_vehicle_state(
        db_session,
        redis_client,
        vehicle.id,
        now=T0 + timedelta(seconds=2),
        stale_threshold_s=15,
        offline_threshold_s=300,
    )
    assert state is not None
    assert state.latitude == 11.0  # the newer sample, not the late-arriving older one


async def test_timestamp_outside_skew_tolerance_is_rejected_and_not_persisted(
    db_session: AsyncSession, redis_client: redis_asyncio.Redis
) -> None:
    vehicle = make_vehicle()
    await flush(db_session, vehicle)
    payload = make_telemetry_event(vehicle.id, ts=T0 - timedelta(hours=1))

    with pytest.raises(TelemetryRejected):
        await _ingest(db_session, redis_client, payload)

    assert await _count_rows(db_session, vehicle.id) == 0


async def test_unknown_vehicle_is_rejected_and_not_persisted(
    db_session: AsyncSession, redis_client: redis_asyncio.Redis
) -> None:
    import uuid

    unknown_vehicle_id = uuid.uuid4()
    payload = make_telemetry_event(unknown_vehicle_id, ts=T0)

    with pytest.raises(UnknownVehicleError):
        await _ingest(db_session, redis_client, payload)

    assert await _count_rows(db_session, unknown_vehicle_id) == 0


async def test_segment_association_matches_a_nearby_segment(
    db_session: AsyncSession, redis_client: redis_asyncio.Redis
) -> None:
    a = make_intersection(20.0, 20.0)
    b = make_intersection(20.001, 20.001)
    await flush(db_session, a, b)
    from shapely.geometry import Point

    segment = make_road_segment(a, b, Point(20.0, 20.0), Point(20.001, 20.001), is_oneway=False)
    await flush(db_session, segment)
    vehicle = make_vehicle()
    await flush(db_session, vehicle)

    payload = make_telemetry_event(vehicle.id, lat=20.0002, lon=20.0002, ts=T0)
    result = await _ingest(db_session, redis_client, payload)

    assert result.road_segment_id == segment.id


async def test_segment_association_is_none_when_nothing_within_radius(
    db_session: AsyncSession, redis_client: redis_asyncio.Redis
) -> None:
    vehicle = make_vehicle()
    await flush(db_session, vehicle)
    payload = make_telemetry_event(vehicle.id, lat=-40.0, lon=-40.0, ts=T0)

    result = await _ingest(db_session, redis_client, payload)

    assert result.status == "accepted"
    assert result.road_segment_id is None


async def test_get_vehicle_state_returns_none_when_never_reported(
    db_session: AsyncSession, redis_client: redis_asyncio.Redis
) -> None:
    vehicle = make_vehicle()
    await flush(db_session, vehicle)

    state = await get_vehicle_state(
        db_session, redis_client, vehicle.id, now=T0, stale_threshold_s=15, offline_threshold_s=300
    )

    assert state is None


async def test_get_vehicle_state_falls_back_to_postgres_on_cache_miss(
    db_session: AsyncSession, redis_client: redis_asyncio.Redis
) -> None:
    """Simulates a cold/flushed Redis cache: delete the key the pipeline
    just wrote, then confirm state is still reconstructable from the
    durable `telemetry` table (TASK-204 §11/§26)."""
    vehicle = make_vehicle()
    await flush(db_session, vehicle)
    payload = make_telemetry_event(vehicle.id, lat=15.0, lon=15.0, ts=T0)
    await _ingest(db_session, redis_client, payload)

    await redis_client.delete(f"aura:vehicle_state:{vehicle.id}")

    state = await get_vehicle_state(
        db_session, redis_client, vehicle.id, now=T0, stale_threshold_s=15, offline_threshold_s=300
    )
    assert state is not None
    assert state.latitude == 15.0


async def test_get_vehicle_state_freshness_classification(
    db_session: AsyncSession, redis_client: redis_asyncio.Redis
) -> None:
    vehicle = make_vehicle()
    await flush(db_session, vehicle)
    payload = make_telemetry_event(vehicle.id, ts=T0)
    await _ingest(db_session, redis_client, payload)

    live = await get_vehicle_state(
        db_session, redis_client, vehicle.id, now=T0, stale_threshold_s=15, offline_threshold_s=300
    )
    stale = await get_vehicle_state(
        db_session,
        redis_client,
        vehicle.id,
        now=T0 + timedelta(seconds=200),
        stale_threshold_s=15,
        offline_threshold_s=300,
    )
    offline = await get_vehicle_state(
        db_session,
        redis_client,
        vehicle.id,
        now=T0 + timedelta(seconds=301),
        stale_threshold_s=15,
        offline_threshold_s=300,
    )

    assert live is not None and live.freshness == "live"
    assert stale is not None and stale.freshness == "stale"
    assert offline is not None and offline.freshness == "offline"


async def test_get_vehicle_state_resolves_active_assignment(
    db_session: AsyncSession, redis_client: redis_asyncio.Redis
) -> None:
    """Assignment is resolved on read from TASK-201's VehicleAssignment,
    never stored on the telemetry row itself (TASK-204 §13/§15)."""
    vehicle = make_vehicle()
    route = make_route()
    calendar = make_service_calendar()
    await flush(db_session, vehicle, route, calendar)
    assignment = make_vehicle_assignment(vehicle, route, calendar)
    await flush(db_session, assignment)

    payload = make_telemetry_event(vehicle.id, ts=T0)
    await _ingest(db_session, redis_client, payload)

    state = await get_vehicle_state(
        db_session, redis_client, vehicle.id, now=T0, stale_threshold_s=15, offline_threshold_s=300
    )

    assert state is not None
    assert state.active_assignment is not None
    assert state.active_assignment.route_id == route.id
    assert state.active_assignment.service_calendar_id == calendar.id


async def test_get_vehicle_state_no_assignment_is_none(
    db_session: AsyncSession, redis_client: redis_asyncio.Redis
) -> None:
    vehicle = make_vehicle()
    await flush(db_session, vehicle)
    payload = make_telemetry_event(vehicle.id, ts=T0)
    await _ingest(db_session, redis_client, payload)

    state = await get_vehicle_state(
        db_session, redis_client, vehicle.id, now=T0, stale_threshold_s=15, offline_threshold_s=300
    )

    assert state is not None
    assert state.active_assignment is None
