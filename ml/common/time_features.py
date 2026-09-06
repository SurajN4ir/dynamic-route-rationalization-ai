"""Deterministic time-context features - see
docs/architecture/TASK205_DESIGN.md §4.

Everything here is UTC-only. AURA has no configured local operational
timezone anywhere in the actual codebase (`Settings` has no timezone
field, every `timestamptz` column is handled as UTC throughout TASK-201-
204) - inventing a local-time convention here would be exactly the kind
of silently-assumed architecture this project's process explicitly
forbids. If a specific deployment timezone is chosen later, these
functions are the one place that would change.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

# Default weekday rush-hour windows, UTC hour-of-day, half-open [start, end).
# A deliberately simple, explicit, documented policy choice - not empirically
# tuned, and trivially overridable by passing different windows.
DEFAULT_PEAK_HOUR_WINDOWS: tuple[tuple[int, int], ...] = ((7, 10), (17, 20))


@dataclass(frozen=True, slots=True)
class TemporalFeatures:
    hour_of_day: int
    day_of_week: int  # ISO: 0=Monday .. 6=Sunday
    is_weekend: bool
    is_peak: bool


def compute_temporal_features(
    ts: datetime, *, peak_hour_windows: tuple[tuple[int, int], ...] = DEFAULT_PEAK_HOUR_WINDOWS
) -> TemporalFeatures:
    """`ts` must be timezone-aware; this raises rather than silently
    guessing a timezone for a naive value (same policy TASK-204's
    telemetry validation already established)."""
    if ts.tzinfo is None:
        raise ValueError("compute_temporal_features requires a timezone-aware timestamp")

    day_of_week = ts.weekday()
    is_weekend = day_of_week >= 5
    is_peak = (not is_weekend) and any(start <= ts.hour < end for start, end in peak_hour_windows)
    return TemporalFeatures(
        hour_of_day=ts.hour, day_of_week=day_of_week, is_weekend=is_weekend, is_peak=is_peak
    )
