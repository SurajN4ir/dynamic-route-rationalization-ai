"""Unit tests for app.telemetry.state's pure (de)serialization - the
Redis cache round-trip, exercised without a real Redis connection."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.telemetry.state import CurrentVehicleState, _from_json, _to_json


def test_round_trip_preserves_all_fields() -> None:
    state = CurrentVehicleState(
        vehicle_id=uuid.uuid4(),
        latitude=12.9716,
        longitude=77.5946,
        speed_mps=8.3,
        heading_deg=142.0,
        ts=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
        road_segment_id=uuid.uuid4(),
        segment_distance_m=4.2,
    )

    restored = _from_json(_to_json(state))

    assert restored == state


def test_round_trip_with_null_optional_fields() -> None:
    state = CurrentVehicleState(
        vehicle_id=uuid.uuid4(),
        latitude=0.0,
        longitude=0.0,
        speed_mps=0.0,
        heading_deg=None,
        ts=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
        road_segment_id=None,
        segment_distance_m=None,
    )

    restored = _from_json(_to_json(state))

    assert restored == state
