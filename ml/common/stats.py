"""Feature-dataset inspection - see docs/architecture/TASK205_DESIGN.md
§22. Reports only what's actually present in a generated dataset - never
fabricates a quality metric (TASK-205 §22/§30)."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_NUMERIC_SUFFIXES_EXCLUDED = {"road_segment_id", "feature_ts", "road_class"}


@dataclass(frozen=True, slots=True)
class ColumnStats:
    name: str
    non_missing_count: int
    missing_count: int
    min_value: float | None = None
    max_value: float | None = None
    mean_value: float | None = None


@dataclass(frozen=True, slots=True)
class DatasetStats:
    row_count: int
    entity_count: int
    time_range: tuple[str, str] | None
    feature_set_version: str
    columns: list[ColumnStats]
    target_availability: dict[str, float]  # column name -> fraction non-missing


def _read_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _try_float(value: str) -> float | None:
    if value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def compute_dataset_stats(csv_path: Path, manifest: dict[str, Any]) -> DatasetStats:
    rows = _read_rows(csv_path)
    columns = manifest["columns"]

    entity_ids = {row["road_segment_id"] for row in rows if row.get("road_segment_id")}
    timestamps = sorted(row["feature_ts"] for row in rows if row.get("feature_ts"))
    time_range = (timestamps[0], timestamps[-1]) if timestamps else None

    column_stats: list[ColumnStats] = []
    target_availability: dict[str, float] = {}
    for column in columns:
        values = [row.get(column, "") for row in rows]
        missing = sum(1 for v in values if v == "")
        non_missing = len(values) - missing

        numeric_values: list[float] = []
        if column not in _NUMERIC_SUFFIXES_EXCLUDED:
            for raw_value in values:
                parsed = _try_float(raw_value)
                if parsed is not None:
                    numeric_values.append(parsed)

        column_stats.append(
            ColumnStats(
                name=column,
                non_missing_count=non_missing,
                missing_count=missing,
                min_value=min(numeric_values) if numeric_values else None,
                max_value=max(numeric_values) if numeric_values else None,
                mean_value=(sum(numeric_values) / len(numeric_values)) if numeric_values else None,
            )
        )
        if column.startswith("target_"):
            target_availability[column] = non_missing / len(values) if values else 0.0

    return DatasetStats(
        row_count=len(rows),
        entity_count=len(entity_ids),
        time_range=time_range,
        feature_set_version=manifest.get("feature_set_version", "unknown"),
        columns=column_stats,
        target_availability=target_availability,
    )
