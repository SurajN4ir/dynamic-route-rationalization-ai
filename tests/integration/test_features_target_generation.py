"""Integration tests for ml.common.targets.generate_traffic_target against
real PostGIS - the only implemented deterministic label generator
(TASK-205 §11)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from shapely.geometry import Point
from sqlalchemy.ext.asyncio import AsyncSession

from ml.common.targets import generate_traffic_target
from tests.fixtures.telemetry import make_telemetry_row
from tests.fixtures.transportation import flush, make_intersection, make_road_segment, make_vehicle

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


async def _make_segment(db_session: AsyncSession):
    a = make_intersection(6.0, 6.0)
    b = make_intersection(6.001, 6.001)
    await flush(db_session, a, b)
    segment = make_road_segment(a, b, Point(6.0, 6.0), Point(6.001, 6.001))
    await flush(db_session, segment)
    return segment


async def test_target_is_none_when_no_future_observations_exist(db_session: AsyncSession) -> None:
    segment = await _make_segment(db_session)

    target = await generate_traffic_target(db_session, segment.id, feature_ts=T0, horizon_s=300)

    assert target is None


async def test_target_averages_observations_in_the_future_window(db_session: AsyncSession) -> None:
    segment = await _make_segment(db_session)
    vehicle = make_vehicle()
    await flush(db_session, vehicle)
    # horizon=300s -> window [T0+300s, T0+600s)
    in_window_1 = make_telemetry_row(
        vehicle.id, ts=T0 + timedelta(seconds=350), speed_mps=10.0, road_segment_id=segment.id
    )
    in_window_2 = make_telemetry_row(
        vehicle.id, ts=T0 + timedelta(seconds=500), speed_mps=20.0, road_segment_id=segment.id
    )
    await flush(db_session, in_window_1, in_window_2)

    target = await generate_traffic_target(db_session, segment.id, feature_ts=T0, horizon_s=300)

    assert target == 15.0


async def test_target_excludes_observations_before_the_horizon_window(
    db_session: AsyncSession,
) -> None:
    segment = await _make_segment(db_session)
    vehicle = make_vehicle()
    await flush(db_session, vehicle)
    # This is the "current" observation, not part of the +300s target window.
    at_feature_ts = make_telemetry_row(
        vehicle.id, ts=T0 + timedelta(seconds=1), speed_mps=999.0, road_segment_id=segment.id
    )
    in_window = make_telemetry_row(
        vehicle.id, ts=T0 + timedelta(seconds=350), speed_mps=10.0, road_segment_id=segment.id
    )
    await flush(db_session, at_feature_ts, in_window)

    target = await generate_traffic_target(db_session, segment.id, feature_ts=T0, horizon_s=300)

    assert target == 10.0


async def test_target_excludes_observations_after_the_window_end(db_session: AsyncSession) -> None:
    segment = await _make_segment(db_session)
    vehicle = make_vehicle()
    await flush(db_session, vehicle)
    in_window = make_telemetry_row(
        vehicle.id, ts=T0 + timedelta(seconds=350), speed_mps=10.0, road_segment_id=segment.id
    )
    after_window = make_telemetry_row(
        vehicle.id, ts=T0 + timedelta(seconds=700), speed_mps=999.0, road_segment_id=segment.id
    )
    await flush(db_session, in_window, after_window)

    target = await generate_traffic_target(db_session, segment.id, feature_ts=T0, horizon_s=300)

    assert target == 10.0


async def test_different_horizons_use_different_windows(db_session: AsyncSession) -> None:
    segment = await _make_segment(db_session)
    vehicle = make_vehicle()
    await flush(db_session, vehicle)
    # +5min window: [300,600); +15min window: [900,1200)
    five_min = make_telemetry_row(
        vehicle.id, ts=T0 + timedelta(seconds=400), speed_mps=10.0, road_segment_id=segment.id
    )
    fifteen_min = make_telemetry_row(
        vehicle.id, ts=T0 + timedelta(seconds=1000), speed_mps=30.0, road_segment_id=segment.id
    )
    await flush(db_session, five_min, fifteen_min)

    target_5m = await generate_traffic_target(db_session, segment.id, feature_ts=T0, horizon_s=300)
    target_15m = await generate_traffic_target(db_session, segment.id, feature_ts=T0, horizon_s=900)

    assert target_5m == 10.0
    assert target_15m == 30.0
