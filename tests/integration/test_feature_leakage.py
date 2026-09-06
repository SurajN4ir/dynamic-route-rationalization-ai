"""Leakage-prevention tests - TASK-205 §7, explicitly mandatory. Proves
that a feature row at timestamp T can never see telemetry stamped at or
after T, in every place data crosses that boundary: the windowed
aggregates, the latest-observation lookup, and the full dataset
generator. A future observation may only ever be used as a *target*
(ml.common.targets), never as a feature.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from shapely.geometry import Point
from sqlalchemy.ext.asyncio import AsyncSession

from ml.common.dataset import DatasetGenerationConfig, generate_road_segment_dataset
from ml.common.targets import TARGET_WINDOW_S, generate_traffic_target
from ml.common.telemetry_features import load_telemetry_derived_features
from tests.fixtures.telemetry import make_telemetry_row
from tests.fixtures.transportation import flush, make_intersection, make_road_segment, make_vehicle

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


async def _make_segment(db_session: AsyncSession):
    a = make_intersection(9.0, 9.0)
    b = make_intersection(9.001, 9.001)
    await flush(db_session, a, b)
    segment = make_road_segment(a, b, Point(9.0, 9.0), Point(9.001, 9.001))
    await flush(db_session, segment)
    return segment


async def test_observation_exactly_at_t_is_excluded(db_session: AsyncSession) -> None:
    """The boundary is strict: ts < T, not ts <= T."""
    segment = await _make_segment(db_session)
    vehicle = make_vehicle()
    await flush(db_session, vehicle)
    at_boundary = make_telemetry_row(vehicle.id, ts=T0, speed_mps=999.0, road_segment_id=segment.id)
    await flush(db_session, at_boundary)

    features = await load_telemetry_derived_features(db_session, [segment.id], feature_ts=T0)

    assert segment.id not in features  # zero visible observations at T


async def test_observation_one_microsecond_before_t_is_included(db_session: AsyncSession) -> None:
    segment = await _make_segment(db_session)
    vehicle = make_vehicle()
    await flush(db_session, vehicle)
    just_before = make_telemetry_row(
        vehicle.id, ts=T0 - timedelta(microseconds=1), speed_mps=42.0, road_segment_id=segment.id
    )
    await flush(db_session, just_before)

    features = await load_telemetry_derived_features(db_session, [segment.id], feature_ts=T0)

    assert features[segment.id].speed_now_mps == 42.0


async def test_future_observation_never_appears_in_speed_now_or_windows(
    db_session: AsyncSession,
) -> None:
    """A large future spike must not appear in any statistic of a
    feature row computed at T, even though it exists in the same table."""
    segment = await _make_segment(db_session)
    vehicle = make_vehicle()
    await flush(db_session, vehicle)
    past = make_telemetry_row(
        vehicle.id, ts=T0 - timedelta(minutes=2), speed_mps=10.0, road_segment_id=segment.id
    )
    future_spike = make_telemetry_row(
        vehicle.id, ts=T0 + timedelta(minutes=2), speed_mps=999.0, road_segment_id=segment.id
    )
    await flush(db_session, past, future_spike)

    features = await load_telemetry_derived_features(db_session, [segment.id], feature_ts=T0)

    result = features[segment.id]
    assert result.speed_now_mps == 10.0
    assert result.speed_mean_5m == 10.0
    assert result.speed_mean_15m == 10.0
    assert result.observation_count_15m == 1  # not 2 - the future row is invisible


async def test_full_dataset_generator_never_leaks_future_telemetry(
    db_session: AsyncSession,
) -> None:
    """End-to-end version of the same guarantee, through the actual
    dataset generator a researcher would run."""
    segment = await _make_segment(db_session)
    vehicle = make_vehicle()
    await flush(db_session, vehicle)
    past = make_telemetry_row(
        vehicle.id, ts=T0 - timedelta(minutes=1), speed_mps=5.0, road_segment_id=segment.id
    )
    future_spike = make_telemetry_row(
        vehicle.id, ts=T0 + timedelta(minutes=1), speed_mps=999.0, road_segment_id=segment.id
    )
    await flush(db_session, past, future_spike)
    config = DatasetGenerationConfig(start=T0 - timedelta(minutes=5), end=T0, bucket_s=300)

    rows = await generate_road_segment_dataset(db_session, config)

    row = next(r for r in rows if r["road_segment_id"] == str(segment.id))
    assert row["speed_now_mps"] == 5.0
    assert row["speed_mean_5m"] == 5.0
    assert 999.0 not in (row["speed_now_mps"], row["speed_mean_5m"], row["speed_mean_15m"])


async def test_target_generator_only_uses_future_data_never_past(db_session: AsyncSession) -> None:
    """The mirror-image check: the *target* must never accidentally pick
    up the "current" (pre-T) observation instead of a genuinely future
    one - the inverse leakage direction."""
    segment = await _make_segment(db_session)
    vehicle = make_vehicle()
    await flush(db_session, vehicle)
    current = make_telemetry_row(
        vehicle.id, ts=T0 - timedelta(seconds=1), speed_mps=1.0, road_segment_id=segment.id
    )
    future = make_telemetry_row(
        vehicle.id, ts=T0 + timedelta(seconds=350), speed_mps=99.0, road_segment_id=segment.id
    )
    await flush(db_session, current, future)

    target = await generate_traffic_target(db_session, segment.id, feature_ts=T0, horizon_s=300)

    assert target == 99.0  # only the future observation, never the pre-T one


async def test_window_start_boundary_is_inclusive(db_session: AsyncSession) -> None:
    """`[T-900s, T)` - an observation exactly at the window start IS
    included (only the upper bound is exclusive)."""
    segment = await _make_segment(db_session)
    vehicle = make_vehicle()
    await flush(db_session, vehicle)
    at_window_start = make_telemetry_row(
        vehicle.id, ts=T0 - timedelta(seconds=900), speed_mps=7.0, road_segment_id=segment.id
    )
    await flush(db_session, at_window_start)

    features = await load_telemetry_derived_features(db_session, [segment.id], feature_ts=T0)

    assert features[segment.id].observation_count_15m == 1


async def test_observation_before_window_start_is_excluded(db_session: AsyncSession) -> None:
    segment = await _make_segment(db_session)
    vehicle = make_vehicle()
    await flush(db_session, vehicle)
    just_before_window = make_telemetry_row(
        vehicle.id,
        ts=T0 - timedelta(seconds=901),
        speed_mps=7.0,
        road_segment_id=segment.id,
    )
    await flush(db_session, just_before_window)

    features = await load_telemetry_derived_features(db_session, [segment.id], feature_ts=T0)

    assert segment.id not in features


async def test_full_boundary_partition_features_vs_target(db_session: AsyncSession) -> None:
    """The architectural review's exact ask: place telemetry at every
    interesting boundary point around T and T+H, with a distinct speed
    value at each, then prove precisely which ones feed FEATURES, which
    feed the TARGET, and which feed neither - no ambiguity left to infer.

    Horizon under test: H = 300s (the shortest configured horizon).
    Target window: [T+H, T+H+TARGET_WINDOW_S).

    Points (speed value in parens):
        T-eps      (1.0)  -> FEATURES only (last obs strictly before T)
        T          (2.0)  -> neither (features need ts < T; target starts at T+H)
        T+eps      (3.0)  -> neither (too early for the target window)
        T+H-eps    (4.0)  -> neither (still before the target window opens)
        T+H        (5.0)  -> TARGET only (window start is inclusive)
        T+H+eps    (6.0)  -> TARGET only
        T+H+W-eps  (7.0)  -> TARGET only (still inside, window end exclusive)
        T+H+W      (8.0)  -> neither (window end is exclusive)
        T+H+W+eps  (9.0)  -> neither
    """
    segment = await _make_segment(db_session)
    vehicle = make_vehicle()
    await flush(db_session, vehicle)
    eps = timedelta(microseconds=1)
    horizon_s = 300
    window_end_offset = timedelta(seconds=horizon_s + TARGET_WINDOW_S)
    horizon_offset = timedelta(seconds=horizon_s)

    points = [
        (T0 - eps, 1.0),
        (T0, 2.0),
        (T0 + eps, 3.0),
        (T0 + horizon_offset - eps, 4.0),
        (T0 + horizon_offset, 5.0),
        (T0 + horizon_offset + eps, 6.0),
        (T0 + window_end_offset - eps, 7.0),
        (T0 + window_end_offset, 8.0),
        (T0 + window_end_offset + eps, 9.0),
    ]
    rows = [
        make_telemetry_row(vehicle.id, ts=ts, speed_mps=speed, road_segment_id=segment.id)
        for ts, speed in points
    ]
    await flush(db_session, *rows)

    features = await load_telemetry_derived_features(db_session, [segment.id], feature_ts=T0)
    target = await generate_traffic_target(
        db_session, segment.id, feature_ts=T0, horizon_s=horizon_s
    )

    # FEATURES: only the T-eps observation (1.0) is visible.
    result = features[segment.id]
    assert result.speed_now_mps == 1.0
    assert result.speed_mean_5m == 1.0
    assert result.speed_mean_15m == 1.0
    assert result.observation_count_15m == 1

    # TARGET: only T+H, T+H+eps, T+H+W-eps (5.0, 6.0, 7.0) are visible.
    assert target == (5.0 + 6.0 + 7.0) / 3
