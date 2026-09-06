"""Integration tests for app.repositories.telemetry.get_segment_observation
- the "network state" concept TASK-204 §23 establishes: observed vehicle
count and mean speed for a road segment over a trailing time window. This
is aggregation over already-persisted telemetry, not a prediction."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import redis.asyncio as redis_asyncio
from shapely.geometry import Point
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.telemetry import get_segment_observation
from app.telemetry.pipeline import ingest_telemetry
from tests.fixtures.telemetry import make_telemetry_event
from tests.fixtures.transportation import flush, make_intersection, make_road_segment, make_vehicle

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

_PIPELINE_KWARGS: dict[str, Any] = {
    "max_speed_mps": 40.0,
    "max_clock_skew_past_s": 30,
    "max_clock_skew_future_s": 5,
    "segment_search_radius_m": 50.0,
    "state_cache_ttl_s": 1800,
}


async def test_segment_observation_aggregates_recent_vehicles(
    db_session: AsyncSession, redis_client: redis_asyncio.Redis
) -> None:
    a = make_intersection(30.0, 30.0)
    b = make_intersection(30.001, 30.001)
    await flush(db_session, a, b)
    segment = make_road_segment(a, b, Point(30.0, 30.0), Point(30.001, 30.001), is_oneway=False)
    await flush(db_session, segment)
    vehicle_1 = make_vehicle()
    vehicle_2 = make_vehicle()
    await flush(db_session, vehicle_1, vehicle_2)

    for vehicle, speed in ((vehicle_1, 10.0), (vehicle_2, 20.0)):
        payload = make_telemetry_event(vehicle.id, lat=30.0002, lon=30.0002, ts=T0, speed_mps=speed)
        await ingest_telemetry(db_session, redis_client, payload, now=T0, **_PIPELINE_KWARGS)

    count, mean_speed = await get_segment_observation(db_session, segment.id, window_s=3600, now=T0)

    assert count == 2
    assert mean_speed == 15.0


async def test_segment_observation_excludes_samples_outside_window(
    db_session: AsyncSession, redis_client: redis_asyncio.Redis
) -> None:
    a = make_intersection(31.0, 31.0)
    b = make_intersection(31.001, 31.001)
    await flush(db_session, a, b)
    segment = make_road_segment(a, b, Point(31.0, 31.0), Point(31.001, 31.001), is_oneway=False)
    await flush(db_session, segment)
    vehicle = make_vehicle()
    await flush(db_session, vehicle)

    payload = make_telemetry_event(vehicle.id, lat=31.0002, lon=31.0002, ts=T0, speed_mps=10.0)
    await ingest_telemetry(db_session, redis_client, payload, now=T0, **_PIPELINE_KWARGS)

    count, mean_speed = await get_segment_observation(
        db_session, segment.id, window_s=60, now=T0 + timedelta(minutes=10)
    )

    assert count == 0
    assert mean_speed is None


async def test_segment_observation_empty_when_no_telemetry(db_session: AsyncSession) -> None:
    a = make_intersection(32.0, 32.0)
    b = make_intersection(32.001, 32.001)
    await flush(db_session, a, b)
    segment = make_road_segment(a, b, Point(32.0, 32.0), Point(32.001, 32.001), is_oneway=False)
    await flush(db_session, segment)

    count, mean_speed = await get_segment_observation(db_session, segment.id, window_s=3600, now=T0)

    assert count == 0
    assert mean_speed is None
