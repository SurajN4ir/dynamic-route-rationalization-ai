"""Deterministic dataset generation - see
docs/architecture/TASK205_DESIGN.md §16/§18.

canonical data + telemetry -> feature generator -> training dataset
(TASK-205's own diagram). Only the road_segment x timestamp / traffic
grain is implemented end-to-end (TASK-205 §1.A is the only family with
complete source data today - see ml/common/targets.py). Static features
and the TASK-203 graph are loaded once per run, not once per row/bucket
(TASK-205 §20).

No new Postgres table: per doc 07 §7.7 ("v1 does not require a dedicated
feature-store product") and `data/features/README.md`'s own existing
placeholder text ("DVC-tracked feature tables consumed by ml/ training
scripts"), a generated dataset is a plain CSV + a JSON manifest written to
a directory (default `data/features/`), not a database write.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ml.common.contract import FEATURE_SET_VERSION, ROAD_SEGMENT_FEATURE_CONTRACT
from ml.common.static_features import load_static_segment_features
from ml.common.targets import TARGET_HORIZONS_S, TARGET_WINDOW_S, generate_traffic_target
from ml.common.telemetry_features import (
    WINDOW_LONG_S,
    WINDOW_SHORT_S,
    load_telemetry_derived_features,
)
from ml.common.time_features import compute_temporal_features

GRAIN = "road_segment_x_timestamp"

# TASK-205 architectural review (target semantics check) §5: this is a
# training-data *eligibility* rule, not an incidental implementation
# detail - it determines which (segment, timestamp) pairs the dataset can
# even represent. Written into every manifest (see write_dataset) so a
# consumer never has to go find this docstring to understand why the
# dataset covers "observed segments," not the full network at every
# timestamp.
ROW_ELIGIBILITY_RULE = (
    f"A (road_segment, feature_ts) row is included only if at least one "
    f"telemetry observation exists on that segment within the {WINDOW_LONG_S}s "
    f"window ending at feature_ts (ts < feature_ts, per TASK-205's leakage "
    f"boundary). Segments/timestamps without such history are omitted "
    f"entirely - never zero-filled or imputed. This means the dataset "
    f"represents observed segments at observed times, not a complete grid "
    f"of the whole network at every bucket; do not treat an absent row as "
    f"evidence of zero traffic."
)

TARGET_DEFINITION_NOTE = (
    f"target_traffic_speed_mps_h<horizon_s> = mean observed speed over "
    f"[feature_ts+horizon_s, feature_ts+horizon_s+{TARGET_WINDOW_S}s), a "
    f"strictly-future window with zero overlap with the feature side's "
    f"ts < feature_ts boundary. Empty/null when zero observations fall in "
    f"that window - this reflects a present feature row with unavailable "
    f"future data (e.g. the underlying telemetry simply doesn't extend "
    f"that far forward yet), never a fabricated value, and does not cause "
    f"the row itself to be dropped."
)


@dataclass(frozen=True, slots=True)
class DatasetGenerationConfig:
    start: datetime
    end: datetime
    bucket_s: int = 300
    horizons_s: tuple[int, ...] = TARGET_HORIZONS_S

    def __post_init__(self) -> None:
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("DatasetGenerationConfig requires timezone-aware start/end")
        if self.end <= self.start:
            raise ValueError("end must be after start")
        if self.bucket_s <= 0:
            raise ValueError("bucket_s must be positive")


def _bucket_timestamps(config: DatasetGenerationConfig) -> list[datetime]:
    """Bucket boundaries are T's own upper bound (TASK-205 §6) - the
    first bucket is `start + bucket_s`, not `start` itself, so every
    bucket has a well-defined preceding window."""
    timestamps = []
    t = config.start + timedelta(seconds=config.bucket_s)
    while t <= config.end:
        timestamps.append(t)
        t += timedelta(seconds=config.bucket_s)
    return timestamps


async def generate_road_segment_dataset(
    session: AsyncSession, config: DatasetGenerationConfig
) -> list[dict[str, Any]]:
    """Deterministic: the same (canonical data, telemetry, config)
    always produces the same rows in the same order (segments ordered
    by id, buckets ordered chronologically) - verified by
    tests/integration/test_dataset_generation.py's determinism test."""
    static_by_segment = await load_static_segment_features(session)
    all_segment_ids = sorted(static_by_segment.keys(), key=str)

    rows: list[dict[str, Any]] = []
    for feature_ts in _bucket_timestamps(config):
        telemetry_by_segment = await load_telemetry_derived_features(
            session, all_segment_ids, feature_ts=feature_ts
        )
        for segment_id in all_segment_ids:
            dynamic = telemetry_by_segment.get(segment_id)
            if dynamic is None:
                continue  # no recent observation basis - omit, don't fabricate (§26)

            static = static_by_segment[segment_id]
            temporal = compute_temporal_features(feature_ts)

            row: dict[str, Any] = {
                "road_segment_id": str(segment_id),
                "feature_ts": feature_ts.isoformat(),
                "length_m": static.length_m,
                "road_class": static.road_class,
                "lanes": static.lanes,
                "maxspeed_kph": static.maxspeed_kph,
                "is_oneway": static.is_oneway,
                "start_intersection_degree": static.start_intersection_degree,
                "end_intersection_degree": static.end_intersection_degree,
                "hour_of_day": temporal.hour_of_day,
                "day_of_week": temporal.day_of_week,
                "is_weekend": temporal.is_weekend,
                "is_peak": temporal.is_peak,
                "speed_now_mps": dynamic.speed_now_mps,
                "age_s": dynamic.age_s,
                "speed_mean_5m": dynamic.speed_mean_5m,
                "speed_mean_15m": dynamic.speed_mean_15m,
                "speed_std_15m": dynamic.speed_std_15m,
                "vehicle_count_5m": dynamic.vehicle_count_5m,
                "vehicle_count_15m": dynamic.vehicle_count_15m,
                "observation_count_15m": dynamic.observation_count_15m,
            }
            for horizon_s in config.horizons_s:
                target = await generate_traffic_target(
                    session, segment_id, feature_ts=feature_ts, horizon_s=horizon_s
                )
                row[f"target_traffic_speed_mps_h{horizon_s}"] = target

            rows.append(row)
    return rows


def _csv_fieldnames(config: DatasetGenerationConfig) -> list[str]:
    fields = [f.name for f in ROAD_SEGMENT_FEATURE_CONTRACT]
    fields += [f"target_traffic_speed_mps_h{h}" for h in config.horizons_s]
    return fields


def write_dataset(
    rows: list[dict[str, Any]], config: DatasetGenerationConfig, out_dir: Path
) -> tuple[Path, Path]:
    """Writes `dataset.csv` + `manifest.json` into `out_dir`. Returns
    (csv_path, manifest_path). Never writes an empty fieldname set even
    for zero rows, so an empty-but-valid dataset is still inspectable."""
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "dataset.csv"
    manifest_path = out_dir / "manifest.json"

    fieldnames = _csv_fieldnames(config)
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: ("" if v is None else v) for k, v in row.items()})

    entity_ids = {row["road_segment_id"] for row in rows}
    manifest = {
        "feature_set_version": FEATURE_SET_VERSION,
        "grain": GRAIN,
        "generated_at": datetime.now(UTC).isoformat(),
        "range_start": config.start.isoformat(),
        "range_end": config.end.isoformat(),
        "bucket_s": config.bucket_s,
        "horizons_s": list(config.horizons_s),
        "feature_window_s": {"short": WINDOW_SHORT_S, "long": WINDOW_LONG_S},
        "target_window_s": TARGET_WINDOW_S,
        "row_eligibility_rule": ROW_ELIGIBILITY_RULE,
        "target_definition": TARGET_DEFINITION_NOTE,
        "row_count": len(rows),
        "entity_count": len(entity_ids),
        "columns": fieldnames,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return csv_path, manifest_path
