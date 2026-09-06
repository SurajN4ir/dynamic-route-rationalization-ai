"""Ordering and freshness policy - see docs/architecture/TASK204_DESIGN.md
§4/§5. Two distinct, deliberately separate concerns:

- `is_newer`: does this *incoming event* advance the vehicle's current
  state? (an ordering decision, made once per ingested event)
- `classify_freshness`: given how long it's been since the current state
  was last advanced, is that state still live? (a read-time decision,
  made whenever a caller asks "where is this vehicle now" - not a
  property of any single telemetry event)

Both are pure functions of their arguments - no clock reads, no I/O -
so the same inputs always produce the same result.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

Freshness = Literal["live", "stale", "offline"]


def is_newer(incoming_ts: datetime, cached_ts: datetime | None) -> bool:
    """Whether `incoming_ts` should replace `cached_ts` as the vehicle's
    current state. `None` means no state has been recorded yet - anything
    valid becomes the first state. Ties do not advance state (a
    same-timestamp retry is a duplicate, not a new observation)."""
    if cached_ts is None:
        return True
    return incoming_ts > cached_ts


def classify_freshness(
    age_s: float, *, stale_threshold_s: int, offline_threshold_s: int
) -> Freshness:
    """`age_s` is seconds since the current state's timestamp (not since
    the last *attempted* update - an out-of-order/duplicate event that
    didn't advance state doesn't reset this clock)."""
    if age_s <= stale_threshold_s:
        return "live"
    if age_s <= offline_threshold_s:
        return "stale"
    return "offline"
