"""Integration tests for ml.common.dataset.generate_road_segment_dataset
against real PostGIS - end-to-end row shape, bucket iteration, and
determinism (TASK-205 §18/§23's mandatory "same inputs, same output"
requirement)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from shapely.geometry import Point
from sqlalchemy.ext.asyncio import AsyncSession

from ml.common.dataset import DatasetGenerationConfig, generate_road_segment_dataset, write_dataset
from tests.fixtures.telemetry import make_telemetry_row
from tests.fixtures.transportation import flush, make_intersection, make_road_segment, make_vehicle

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


async def _make_segment_with_telemetry(db_session: AsyncSession):
    a = make_intersection(7.0, 7.0)
    b = make_intersection(7.001, 7.001)
    await flush(db_session, a, b)
    segment = make_road_segment(
        a, b, Point(7.0, 7.0), Point(7.001, 7.001), length_m=100.0, is_oneway=False
    )
    await flush(db_session, segment)
    vehicle = make_vehicle()
    await flush(db_session, vehicle)
    row = make_telemetry_row(
        vehicle.id, ts=T0 - timedelta(minutes=1), speed_mps=8.0, road_segment_id=segment.id
    )
    await flush(db_session, row)
    return segment


async def test_generates_one_row_per_segment_per_bucket_with_data(
    db_session: AsyncSession,
) -> None:
    segment = await _make_segment_with_telemetry(db_session)
    config = DatasetGenerationConfig(
        start=T0 - timedelta(minutes=5), end=T0, bucket_s=300, horizons_s=(300,)
    )

    rows = await generate_road_segment_dataset(db_session, config)

    assert len(rows) == 1
    assert rows[0]["road_segment_id"] == str(segment.id)
    assert rows[0]["speed_now_mps"] == 8.0
    assert rows[0]["length_m"] == 100.0


async def test_row_is_present_with_missing_target_when_no_future_data_exists(
    db_session: AsyncSession,
) -> None:
    """Architectural review §4/§6: a row with valid features but no
    future telemetry must still be EMITTED (features are usable on their
    own for inspection/other horizons), with its target column explicitly
    missing - never dropped, never fabricated as 0.0. `_make_segment_with_
    telemetry` gives this segment exactly one observation, at T0-1min,
    and nothing at or after T0 - so every horizon's target window is
    entirely empty."""
    segment = await _make_segment_with_telemetry(db_session)
    config = DatasetGenerationConfig(
        start=T0 - timedelta(minutes=5), end=T0, bucket_s=300, horizons_s=(300, 900)
    )

    rows = await generate_road_segment_dataset(db_session, config)

    assert len(rows) == 1  # the row is NOT dropped for lacking a target
    row = rows[0]
    assert row["road_segment_id"] == str(segment.id)
    assert row["speed_now_mps"] == 8.0  # features are fully present
    assert row["target_traffic_speed_mps_h300"] is None  # target is missing, not 0.0
    assert row["target_traffic_speed_mps_h900"] is None


async def test_manifest_documents_row_eligibility_and_target_semantics(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    """Architectural review §5: the eligibility rule that determines
    which (segment, timestamp) pairs can appear at all must be readable
    from the manifest itself, not only from source comments."""
    await _make_segment_with_telemetry(db_session)
    config = DatasetGenerationConfig(
        start=T0 - timedelta(minutes=5), end=T0, bucket_s=300, horizons_s=(300,)
    )
    rows = await generate_road_segment_dataset(db_session, config)

    _, manifest_path = write_dataset(rows, config, tmp_path / "out")

    import json

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "omitted" in manifest["row_eligibility_rule"]
    assert "900s" in manifest["row_eligibility_rule"]
    assert manifest["target_window_s"] == 300
    assert manifest["feature_window_s"] == {"short": 300, "long": 900}
    assert "never a fabricated value" in manifest["target_definition"]


async def test_multiple_buckets_produce_multiple_rows(db_session: AsyncSession) -> None:
    a = make_intersection(7.5, 7.5)
    b = make_intersection(7.501, 7.501)
    await flush(db_session, a, b)
    segment = make_road_segment(a, b, Point(7.5, 7.5), Point(7.501, 7.501))
    await flush(db_session, segment)
    vehicle = make_vehicle()
    await flush(db_session, vehicle)
    # ts=T0-6m falls inside both the [T0-5m-15m, T0-5m) and [T0-15m, T0)
    # windows, so both buckets have a visible (past, non-leaking) observation.
    row = make_telemetry_row(
        vehicle.id, ts=T0 - timedelta(minutes=6), speed_mps=8.0, road_segment_id=segment.id
    )
    await flush(db_session, row)
    config = DatasetGenerationConfig(
        start=T0 - timedelta(minutes=10), end=T0, bucket_s=300, horizons_s=(300,)
    )

    rows = await generate_road_segment_dataset(db_session, config)

    feature_timestamps = {row["feature_ts"] for row in rows}
    assert len(feature_timestamps) == 2


async def test_target_column_present_for_each_configured_horizon(db_session: AsyncSession) -> None:
    await _make_segment_with_telemetry(db_session)
    config = DatasetGenerationConfig(
        start=T0 - timedelta(minutes=5), end=T0, bucket_s=300, horizons_s=(300, 900)
    )

    rows = await generate_road_segment_dataset(db_session, config)

    assert "target_traffic_speed_mps_h300" in rows[0]
    assert "target_traffic_speed_mps_h900" in rows[0]


async def test_generation_is_deterministic(db_session: AsyncSession) -> None:
    """Architectural review §7: identical feature values, identical
    target values, and identical ordering (`==` on a list of dicts checks
    all three - a reordered or value-shifted result would fail)."""
    await _make_segment_with_telemetry(db_session)
    config = DatasetGenerationConfig(
        start=T0 - timedelta(minutes=10), end=T0, bucket_s=300, horizons_s=(300, 900)
    )

    first = await generate_road_segment_dataset(db_session, config)
    second = await generate_road_segment_dataset(db_session, config)

    assert first == second
    assert [r["road_segment_id"] for r in first] == [r["road_segment_id"] for r in second]
    assert [r["feature_ts"] for r in first] == [r["feature_ts"] for r in second]


async def test_generation_is_deterministic_including_csv_and_manifest(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    """Architectural review §7, at the artifact level: two independent
    `write_dataset` calls from unchanged data produce byte-identical CSVs
    and manifests identical in every field except `generated_at` (which
    is provenance metadata - a real wall-clock timestamp, not a derived
    feature/target value, so it is expected and correct for it to differ
    between two separate generation runs)."""
    await _make_segment_with_telemetry(db_session)
    config = DatasetGenerationConfig(
        start=T0 - timedelta(minutes=10), end=T0, bucket_s=300, horizons_s=(300, 900)
    )

    first_rows = await generate_road_segment_dataset(db_session, config)
    second_rows = await generate_road_segment_dataset(db_session, config)
    first_csv, first_manifest_path = write_dataset(first_rows, config, tmp_path / "first")
    second_csv, second_manifest_path = write_dataset(second_rows, config, tmp_path / "second")

    assert first_csv.read_bytes() == second_csv.read_bytes()

    import json

    first_manifest = json.loads(first_manifest_path.read_text(encoding="utf-8"))
    second_manifest = json.loads(second_manifest_path.read_text(encoding="utf-8"))
    first_manifest.pop("generated_at")
    second_manifest.pop("generated_at")
    assert first_manifest == second_manifest


async def test_write_dataset_produces_csv_and_manifest(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    await _make_segment_with_telemetry(db_session)
    config = DatasetGenerationConfig(
        start=T0 - timedelta(minutes=5), end=T0, bucket_s=300, horizons_s=(300,)
    )
    rows = await generate_road_segment_dataset(db_session, config)

    csv_path, manifest_path = write_dataset(rows, config, tmp_path / "out")

    assert csv_path.exists()
    assert manifest_path.exists()
    import json

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["row_count"] == len(rows)
    assert manifest["feature_set_version"] == "v1"
    assert manifest["grain"] == "road_segment_x_timestamp"


async def test_no_rows_when_no_telemetry_exists(db_session: AsyncSession) -> None:
    a = make_intersection(8.0, 8.0)
    b = make_intersection(8.001, 8.001)
    await flush(db_session, a, b)
    segment = make_road_segment(a, b, Point(8.0, 8.0), Point(8.001, 8.001))
    await flush(db_session, segment)
    config = DatasetGenerationConfig(
        start=T0 - timedelta(minutes=5), end=T0, bucket_s=300, horizons_s=(300,)
    )

    rows = await generate_road_segment_dataset(db_session, config)

    assert rows == []
