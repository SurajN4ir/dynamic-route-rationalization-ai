"""Integration tests for ml.common.telemetry_features.load_telemetry_derived_features
against real PostGIS - windowed aggregation correctness, latest-observation
lookup, and the "omit rather than fabricate" row-emission rule (TASK-205
§8/§26). Strict leakage boundary tests live separately in
tests/integration/test_feature_leakage.py.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from ml.common.telemetry_features import load_telemetry_derived_features
from tests.fixtures.telemetry import make_telemetry_row
from tests.fixtures.transportation import flush, make_intersection, make_road_segment, make_vehicle

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


async def _make_segment(db_session: AsyncSession):
    from shapely.geometry import Point

    a = make_intersection(5.0, 5.0)
    b = make_intersection(5.001, 5.001)
    await flush(db_session, a, b)
    segment = make_road_segment(a, b, Point(5.0, 5.0), Point(5.001, 5.001))
    await flush(db_session, segment)
    return segment


async def test_segment_with_no_observations_is_omitted(db_session: AsyncSession) -> None:
    segment = await _make_segment(db_session)

    features = await load_telemetry_derived_features(db_session, [segment.id], feature_ts=T0)

    assert segment.id not in features


async def test_speed_now_and_age_from_latest_observation(db_session: AsyncSession) -> None:
    segment = await _make_segment(db_session)
    vehicle = make_vehicle()
    await flush(db_session, vehicle)
    older = make_telemetry_row(
        vehicle.id, ts=T0 - timedelta(minutes=10), speed_mps=10.0, road_segment_id=segment.id
    )
    newer = make_telemetry_row(
        vehicle.id, ts=T0 - timedelta(minutes=2), speed_mps=20.0, road_segment_id=segment.id
    )
    await flush(db_session, older, newer)

    features = await load_telemetry_derived_features(db_session, [segment.id], feature_ts=T0)

    result = features[segment.id]
    assert result.speed_now_mps == 20.0
    assert result.age_s == 120.0


async def test_speed_mean_5m_excludes_observations_outside_5m_but_within_15m(
    db_session: AsyncSession,
) -> None:
    segment = await _make_segment(db_session)
    vehicle = make_vehicle()
    await flush(db_session, vehicle)
    # 10 minutes ago - inside the 15m window, outside the 5m window.
    outside_5m = make_telemetry_row(
        vehicle.id, ts=T0 - timedelta(minutes=10), speed_mps=100.0, road_segment_id=segment.id
    )
    # 2 minutes ago - inside both windows.
    inside_5m = make_telemetry_row(
        vehicle.id, ts=T0 - timedelta(minutes=2), speed_mps=10.0, road_segment_id=segment.id
    )
    await flush(db_session, outside_5m, inside_5m)

    features = await load_telemetry_derived_features(db_session, [segment.id], feature_ts=T0)

    result = features[segment.id]
    assert result.speed_mean_5m == 10.0  # only the inside_5m sample
    assert result.speed_mean_15m == 55.0  # mean of both samples
    assert result.observation_count_15m == 2


async def test_vehicle_count_counts_distinct_vehicles_not_rows(db_session: AsyncSession) -> None:
    segment = await _make_segment(db_session)
    vehicle = make_vehicle()
    await flush(db_session, vehicle)
    row1 = make_telemetry_row(
        vehicle.id, ts=T0 - timedelta(minutes=4), speed_mps=10.0, road_segment_id=segment.id
    )
    row2 = make_telemetry_row(
        vehicle.id, ts=T0 - timedelta(minutes=1), speed_mps=12.0, road_segment_id=segment.id
    )
    await flush(db_session, row1, row2)

    features = await load_telemetry_derived_features(db_session, [segment.id], feature_ts=T0)

    result = features[segment.id]
    assert result.vehicle_count_5m == 1  # same vehicle, two rows
    assert result.observation_count_15m == 2


async def test_speed_std_requires_at_least_two_samples(db_session: AsyncSession) -> None:
    segment = await _make_segment(db_session)
    vehicle = make_vehicle()
    await flush(db_session, vehicle)
    single = make_telemetry_row(
        vehicle.id, ts=T0 - timedelta(minutes=1), speed_mps=10.0, road_segment_id=segment.id
    )
    await flush(db_session, single)

    features = await load_telemetry_derived_features(db_session, [segment.id], feature_ts=T0)

    assert features[segment.id].speed_std_15m is None


async def test_multiple_segments_are_independent(db_session: AsyncSession) -> None:
    segment_a = await _make_segment(db_session)
    segment_b = await _make_segment(db_session)
    vehicle = make_vehicle()
    await flush(db_session, vehicle)
    row_a = make_telemetry_row(
        vehicle.id, ts=T0 - timedelta(minutes=1), speed_mps=10.0, road_segment_id=segment_a.id
    )
    await flush(db_session, row_a)

    features = await load_telemetry_derived_features(
        db_session, [segment_a.id, segment_b.id], feature_ts=T0
    )

    assert segment_a.id in features
    assert segment_b.id not in features
