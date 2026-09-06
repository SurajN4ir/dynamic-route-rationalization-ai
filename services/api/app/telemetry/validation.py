"""Pure telemetry field validation - see docs/architecture/TASK204_DESIGN.md
§6. No database access here; `vehicle_id` existence is checked separately
by the pipeline (app/telemetry/pipeline.py), since that requires a query.

Coordinate range, heading range, and non-negative speed/accuracy are
already enforced by `TelemetryIngestRequest`'s Pydantic field constraints
(structural - always true, never configurable) before this module ever
runs. What's left here is *policy* validation that depends on runtime
config or the current time, neither of which belongs in a Pydantic model:
the speed ceiling (a configurable sensor-error cutoff, not a physical
law) and clock-skew tolerance (inherently relative to "now").
"""

from __future__ import annotations

from datetime import datetime

from app.schemas.telemetry import TelemetryIngestRequest


def validate_fields(
    payload: TelemetryIngestRequest,
    *,
    now: datetime,
    max_speed_mps: float,
    max_clock_skew_past_s: int,
    max_clock_skew_future_s: int,
) -> list[str]:
    """Returns a list of human-readable rejection reasons - empty if the
    payload passes every policy check. Deterministic: the same
    (payload, now, config) always produces the same result."""
    reasons: list[str] = []

    if payload.timestamp.tzinfo is None:
        reasons.append("timestamp must be timezone-aware")
    else:
        age_s = (now - payload.timestamp).total_seconds()
        if age_s > max_clock_skew_past_s:
            reasons.append(
                f"timestamp is {age_s:.1f}s in the past, exceeding the "
                f"{max_clock_skew_past_s}s tolerance"
            )
        elif age_s < -max_clock_skew_future_s:
            reasons.append(
                f"timestamp is {-age_s:.1f}s in the future, exceeding the "
                f"{max_clock_skew_future_s}s tolerance"
            )

    if payload.speed_mps > max_speed_mps:
        reasons.append(
            f"speed_mps {payload.speed_mps} exceeds the configured ceiling of {max_speed_mps}"
        )

    return reasons
