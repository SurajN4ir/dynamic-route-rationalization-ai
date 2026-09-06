"""Future prediction target definitions - see
docs/architecture/TASK205_DESIGN.md §9/§10/§11/§12.

TASK-205 defines targets for all five prediction families doc 01/07
anticipate, but only **implements deterministic label generation for
traffic** - the only family whose required source data actually exists
in the canonical schema today (`telemetry.road_segment_id` +
`vehicle_assignments`/`routes` are not enough to derive a real journey
instance, a route-to-road-segment path, or passenger counts; see each
`TargetDefinition.availability` below for the specific missing
dependency). Calling `generate_traffic_target` on a road segment/window
combination with zero telemetry returns `None` (missing, per §26) - it
never fabricates a value.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.telemetry import Telemetry

TARGET_HORIZONS_S: tuple[int, ...] = (300, 900)  # +5 min, +15 min (TASK-205 §10)

# The future aggregation window's width, in seconds. A named constant, not
# a literal buried in generate_traffic_target(), so the manifest (see
# ml/common/dataset.py) and the target's documented semantics can never
# drift from what the code actually computes.
TARGET_WINDOW_S = 300


class TargetAvailability(StrEnum):
    AVAILABLE = "available"  # deterministic generation implemented today
    DEFERRED = "deferred"  # conceptually defined, generation blocked on missing data


@dataclass(frozen=True, slots=True)
class TargetDefinition:
    name: str
    entity: str
    target_calculation: str
    required_source_data: str
    units: str
    missing_data_behavior: str
    availability: TargetAvailability
    unavailable_reason: str | None = None


TARGET_DEFINITIONS: tuple[TargetDefinition, ...] = (
    TargetDefinition(
        name="traffic_speed",
        entity="road_segment",
        target_calculation=(
            f"mean observed speed on this segment over "
            f"[T+horizon_s, T+horizon_s+{TARGET_WINDOW_S}s) - a deterministic "
            f"future aggregation window, not a single point sample; strictly "
            f"after T (T+horizon_s >= T+300s for the shortest configured "
            f"horizon), with zero overlap with the feature side's ts < T "
            f"boundary"
        ),
        required_source_data="telemetry (TASK-204) - available now",
        units="m/s",
        missing_data_behavior="None if zero observations fall in the target window "
        "(never 0.0 - see TASK-205 §26)",
        availability=TargetAvailability.AVAILABLE,
    ),
    TargetDefinition(
        name="eta",
        entity="vehicle/trip/segment observation",
        target_calculation="time for the vehicle to travel from its current segment "
        "to a specific downstream stop/segment",
        required_source_data="a route-to-road-segment path mapping (which canonical "
        "RoadSegments make up a Route's path, in order) - does not exist; and a "
        "specific journey/trip instance distinct from a standing VehicleAssignment",
        units="seconds",
        missing_data_behavior="not generated - see unavailable_reason",
        availability=TargetAvailability.DEFERRED,
        unavailable_reason="No Route<->RoadSegment path mapping exists in the "
        "canonical schema (routes.geometry is a LineString, not an ordered list of "
        "RoadSegment references), so 'segments remaining until stop X' cannot be "
        "computed. Required later: a route-path table or graph-derived shortest "
        "path from the vehicle's current segment to the target stop's segment.",
    ),
    TargetDefinition(
        name="delay",
        entity="vehicle/route operational observation",
        target_calculation="actual arrival/position time minus scheduled/expected "
        "time, for a specific trip instance",
        required_source_data="a trip instance with a scheduled start time - "
        "doc 04's `trips` table was never created (TASK-201 built "
        "`vehicle_assignments` instead, a standing assignment, not a specific run)",
        units="seconds",
        missing_data_behavior="not generated - see unavailable_reason",
        availability=TargetAvailability.DEFERRED,
        unavailable_reason="No journey-instance concept exists to anchor 'scheduled' "
        "vs 'actual' - VehicleAssignment states which vehicle serves which route on "
        "which calendar, not a specific dated/timed run. Required later: a trips-"
        "equivalent table with a concrete scheduled_start per journey.",
    ),
    TargetDefinition(
        name="demand",
        entity="stop/route",
        target_calculation="passenger boardings/alightings at a stop over a future " "window",
        required_source_data="passenger count observations",
        units="passengers",
        missing_data_behavior="not generated - see unavailable_reason",
        availability=TargetAvailability.DEFERRED,
        unavailable_reason="doc 04's `demand_observations` table was never created "
        "and no passenger-counting sensor/process exists anywhere in this project. "
        "Required later: a passenger observation source (doc 04 §demand_observations, "
        "or a manual/APC data-entry mechanism) before this target can be generated "
        "from anything other than fabricated data - which TASK-205 explicitly must "
        "not do.",
    ),
    TargetDefinition(
        name="bunching",
        entity="vehicle pair on a shared route",
        target_calculation="headway (time/distance gap) between two consecutive "
        "vehicles serving the same route, and whether it degrades below a threshold "
        "within a future horizon",
        required_source_data="an ordered route-path (to know which vehicle is "
        "'ahead') plus each vehicle's progress along it",
        units="seconds (headway) / boolean (bunching event)",
        missing_data_behavior="not generated - see unavailable_reason",
        availability=TargetAvailability.DEFERRED,
        unavailable_reason="Computing headway requires knowing each vehicle's "
        "position *along a shared route path*, not just its nearest road segment - "
        "the same missing route-to-road-segment mapping ETA's target needs. "
        "VehicleAssignment confirms which vehicles share a route, but not their "
        "relative order/progress along it.",
    ),
)


async def generate_traffic_target(
    session: AsyncSession, road_segment_id: uuid.UUID, *, feature_ts: datetime, horizon_s: int
) -> float | None:
    """The only implemented target generator (TASK-205 §11).

    Exact semantics: mean speed over the half-open window
    `[feature_ts + horizon_s, feature_ts + horizon_s + TARGET_WINDOW_S)`.
    `horizon_s` is always >= 300s (the smallest configured value in
    `TARGET_HORIZONS_S`), so `window_start` is always strictly after
    `feature_ts` - there is no timestamp that is simultaneously eligible
    as a feature (`ts < feature_ts`) and as part of this window. Returns
    `None` (never `0.0` or any other fabricated value) when zero
    observations fall inside the window - a missing target on an
    otherwise-present feature row (TASK-205 §26/§30's "no fabricated
    data" rule applies to targets exactly as it does to features)."""
    if feature_ts.tzinfo is None:
        raise ValueError("feature_ts must be timezone-aware")

    window_start = feature_ts + timedelta(seconds=horizon_s)
    window_end = window_start + timedelta(seconds=TARGET_WINDOW_S)

    stmt = select(func.avg(Telemetry.speed_mps)).where(
        Telemetry.road_segment_id == road_segment_id,
        Telemetry.ts >= window_start,
        Telemetry.ts < window_end,
    )
    result = await session.execute(stmt)
    mean_speed = result.scalar_one_or_none()
    return float(mean_speed) if mean_speed is not None else None
