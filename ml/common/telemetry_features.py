"""Telemetry-derived (OBSERVED/DERIVED) features - see
docs/architecture/TASK205_DESIGN.md §5/§7/§8. This is the leakage-critical
module: every query here is filtered to `ts < T` (strict), never `<= T` -
a feature row at T must never see an observation stamped exactly at T or
later. `tests/unit/test_feature_leakage.py`/
`tests/integration/test_feature_leakage.py` exist specifically to prove
this boundary holds.

Two windows only (5 and 15 minutes) - matching doc 01's shortest traffic
horizons (5/15/30/60 min) and TASK-204's already-established stale/
offline thresholds, not an arbitrarily large window sweep (TASK-205 §8's
explicit "avoid unnecessary feature explosion").

Bulk, not per-row: one query for the windowed aggregates (conditional
`FILTER (WHERE ...)` for both windows in a single pass), one query for
the latest-observation-per-segment (`DISTINCT ON`) - never one query per
road segment (TASK-205 §20).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.telemetry import Telemetry

WINDOW_SHORT_S = 300  # 5 minutes
WINDOW_LONG_S = 900  # 15 minutes


@dataclass(frozen=True, slots=True)
class TelemetryDerivedFeatures:
    road_segment_id: uuid.UUID
    speed_now_mps: float | None
    age_s: float | None
    speed_mean_5m: float | None
    speed_mean_15m: float | None
    speed_std_15m: float | None
    vehicle_count_5m: int
    vehicle_count_15m: int
    observation_count_15m: int


async def load_telemetry_derived_features(
    session: AsyncSession, road_segment_ids: list[uuid.UUID], *, feature_ts: datetime
) -> dict[uuid.UUID, TelemetryDerivedFeatures]:
    """`feature_ts` is T - the leakage boundary. Every row returned here
    is computed exclusively from `telemetry` rows with `ts < feature_ts`."""
    if not road_segment_ids:
        return {}
    if feature_ts.tzinfo is None:
        raise ValueError("feature_ts must be timezone-aware")

    window_start = feature_ts - timedelta(seconds=WINDOW_LONG_S)
    short_window_start = feature_ts - timedelta(seconds=WINDOW_SHORT_S)

    in_short_window = Telemetry.ts >= short_window_start

    agg_stmt = (
        select(
            Telemetry.road_segment_id,
            func.avg(Telemetry.speed_mps).filter(in_short_window).label("speed_mean_5m"),
            func.avg(Telemetry.speed_mps).label("speed_mean_15m"),
            func.stddev_samp(Telemetry.speed_mps).label("speed_std_15m"),
            func.count(func.distinct(Telemetry.vehicle_id))
            .filter(in_short_window)
            .label("vehicle_count_5m"),
            func.count(func.distinct(Telemetry.vehicle_id)).label("vehicle_count_15m"),
            func.count(Telemetry.id).label("observation_count_15m"),
        )
        .where(
            Telemetry.road_segment_id.in_(road_segment_ids),
            Telemetry.ts >= window_start,
            Telemetry.ts < feature_ts,
        )
        .group_by(Telemetry.road_segment_id)
    )
    agg_result = await session.execute(agg_stmt)
    agg_by_segment = {row.road_segment_id: row for row in agg_result.all()}

    latest_subquery = (
        select(
            Telemetry.road_segment_id,
            Telemetry.speed_mps,
            Telemetry.ts,
            func.row_number()
            .over(partition_by=Telemetry.road_segment_id, order_by=Telemetry.ts.desc())
            .label("rn"),
        )
        .where(Telemetry.road_segment_id.in_(road_segment_ids), Telemetry.ts < feature_ts)
        .subquery()
    )
    latest_stmt = select(
        latest_subquery.c.road_segment_id, latest_subquery.c.speed_mps, latest_subquery.c.ts
    ).where(latest_subquery.c.rn == 1)
    latest_result = await session.execute(latest_stmt)
    latest_by_segment = {row.road_segment_id: row for row in latest_result.all()}

    features: dict[uuid.UUID, TelemetryDerivedFeatures] = {}
    for segment_id in road_segment_ids:
        agg = agg_by_segment.get(segment_id)
        latest = latest_by_segment.get(segment_id)

        if agg is None or int(agg.observation_count_15m) == 0:
            # Nothing in either window for this segment at this T - omit
            # this segment from the dataset row entirely rather than
            # emitting a row of nulls (TASK-205 §26/§8 - see dataset.py).
            continue
        observation_count_15m = int(agg.observation_count_15m)

        speed_now = float(latest.speed_mps) if latest is not None else None
        age_s = (feature_ts - latest.ts).total_seconds() if latest is not None else None

        features[segment_id] = TelemetryDerivedFeatures(
            road_segment_id=segment_id,
            speed_now_mps=speed_now,
            age_s=age_s,
            speed_mean_5m=float(agg.speed_mean_5m) if agg.speed_mean_5m is not None else None,
            speed_mean_15m=float(agg.speed_mean_15m) if agg.speed_mean_15m is not None else None,
            speed_std_15m=float(agg.speed_std_15m) if agg.speed_std_15m is not None else None,
            vehicle_count_5m=int(agg.vehicle_count_5m),
            vehicle_count_15m=int(agg.vehicle_count_15m),
            observation_count_15m=observation_count_15m,
        )
    return features
