"""Unit tests for ml.common.stats.compute_dataset_stats - pure file
reading, no database. Writes a small synthetic CSV directly rather than
going through the dataset generator, to isolate stats logic."""

from __future__ import annotations

import csv
from pathlib import Path

from ml.common.stats import compute_dataset_stats

COLUMNS = ["road_segment_id", "feature_ts", "speed_now_mps", "target_traffic_speed_mps_h300"]


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def test_row_and_entity_counts(tmp_path: Path) -> None:
    csv_path = tmp_path / "dataset.csv"
    _write_csv(
        csv_path,
        [
            {
                "road_segment_id": "a",
                "feature_ts": "2026-01-01T00:05:00+00:00",
                "speed_now_mps": "5.0",
                "target_traffic_speed_mps_h300": "6.0",
            },
            {
                "road_segment_id": "b",
                "feature_ts": "2026-01-01T00:10:00+00:00",
                "speed_now_mps": "7.0",
                "target_traffic_speed_mps_h300": "",
            },
        ],
    )
    manifest = {"feature_set_version": "v1", "columns": COLUMNS}

    result = compute_dataset_stats(csv_path, manifest)

    assert result.row_count == 2
    assert result.entity_count == 2
    assert result.time_range == ("2026-01-01T00:05:00+00:00", "2026-01-01T00:10:00+00:00")


def test_missing_values_are_counted_not_imputed(tmp_path: Path) -> None:
    csv_path = tmp_path / "dataset.csv"
    _write_csv(
        csv_path,
        [
            {
                "road_segment_id": "a",
                "feature_ts": "2026-01-01T00:05:00+00:00",
                "speed_now_mps": "",
                "target_traffic_speed_mps_h300": "",
            }
        ],
    )
    manifest = {"feature_set_version": "v1", "columns": COLUMNS}

    result = compute_dataset_stats(csv_path, manifest)

    speed_col = next(c for c in result.columns if c.name == "speed_now_mps")
    assert speed_col.missing_count == 1
    assert speed_col.non_missing_count == 0
    assert speed_col.mean_value is None


def test_target_availability_fraction(tmp_path: Path) -> None:
    csv_path = tmp_path / "dataset.csv"
    _write_csv(
        csv_path,
        [
            {
                "road_segment_id": "a",
                "feature_ts": "t1",
                "speed_now_mps": "1.0",
                "target_traffic_speed_mps_h300": "2.0",
            },
            {
                "road_segment_id": "b",
                "feature_ts": "t2",
                "speed_now_mps": "1.0",
                "target_traffic_speed_mps_h300": "",
            },
        ],
    )
    manifest = {"feature_set_version": "v1", "columns": COLUMNS}

    result = compute_dataset_stats(csv_path, manifest)

    assert result.target_availability["target_traffic_speed_mps_h300"] == 0.5


def test_numeric_min_max_mean(tmp_path: Path) -> None:
    csv_path = tmp_path / "dataset.csv"
    _write_csv(
        csv_path,
        [
            {
                "road_segment_id": "a",
                "feature_ts": "t1",
                "speed_now_mps": "2.0",
                "target_traffic_speed_mps_h300": "",
            },
            {
                "road_segment_id": "b",
                "feature_ts": "t2",
                "speed_now_mps": "4.0",
                "target_traffic_speed_mps_h300": "",
            },
        ],
    )
    manifest = {"feature_set_version": "v1", "columns": COLUMNS}

    result = compute_dataset_stats(csv_path, manifest)

    speed_col = next(c for c in result.columns if c.name == "speed_now_mps")
    assert speed_col.min_value == 2.0
    assert speed_col.max_value == 4.0
    assert speed_col.mean_value == 3.0


def test_empty_dataset_reports_zero_rows(tmp_path: Path) -> None:
    csv_path = tmp_path / "dataset.csv"
    _write_csv(csv_path, [])
    manifest = {"feature_set_version": "v1", "columns": COLUMNS}

    result = compute_dataset_stats(csv_path, manifest)

    assert result.row_count == 0
    assert result.entity_count == 0
    assert result.time_range is None
