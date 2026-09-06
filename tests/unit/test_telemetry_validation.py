"""Unit tests for app.telemetry.validation.validate_fields - pure policy
checks, no database. Coordinate/heading/non-negative-speed range checks
are covered separately as Pydantic field-constraint tests (they reject
before this function ever runs); this module tests what's left: the
configurable speed ceiling and clock-skew tolerance, both of which need a
concrete `now`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.schemas.telemetry import TelemetryIngestRequest
from app.telemetry.validation import validate_fields

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


def _payload(**overrides: object) -> TelemetryIngestRequest:
    defaults: dict[str, object] = {
        "vehicle_id": uuid.uuid4(),
        "timestamp": NOW,
        "latitude": 10.0,
        "longitude": 10.0,
        "speed_mps": 5.0,
        "heading_deg": None,
        "accuracy_m": None,
        "source": "synthetic",
    }
    defaults.update(overrides)
    return TelemetryIngestRequest(**defaults)  # type: ignore[arg-type]


def _validate(payload: TelemetryIngestRequest, *, now: datetime = NOW) -> list[str]:
    return validate_fields(
        payload,
        now=now,
        max_speed_mps=40.0,
        max_clock_skew_past_s=30,
        max_clock_skew_future_s=5,
    )


def test_well_formed_payload_passes() -> None:
    assert _validate(_payload()) == []


def test_speed_over_ceiling_is_rejected() -> None:
    reasons = _validate(_payload(speed_mps=41.0))
    assert any("speed_mps" in r for r in reasons)


def test_speed_at_ceiling_is_accepted() -> None:
    assert _validate(_payload(speed_mps=40.0)) == []


def test_timestamp_too_far_in_the_past_is_rejected() -> None:
    reasons = _validate(_payload(timestamp=NOW - timedelta(seconds=31)))
    assert any("past" in r for r in reasons)


def test_timestamp_at_past_boundary_is_accepted() -> None:
    assert _validate(_payload(timestamp=NOW - timedelta(seconds=30))) == []


def test_timestamp_too_far_in_the_future_is_rejected() -> None:
    reasons = _validate(_payload(timestamp=NOW + timedelta(seconds=6)))
    assert any("future" in r for r in reasons)


def test_timestamp_at_future_boundary_is_accepted() -> None:
    assert _validate(_payload(timestamp=NOW + timedelta(seconds=5))) == []


def test_naive_timestamp_is_rejected() -> None:
    payload = _payload(timestamp=NOW)
    # Pydantic's datetime validation preserves tzinfo; construct a naive
    # instance directly to exercise the guard against it.
    naive = payload.model_copy(update={"timestamp": datetime(2026, 1, 1, 12, 0, 0)})
    reasons = _validate(naive)
    assert any("timezone-aware" in r for r in reasons)


@pytest.mark.parametrize("bad_lat", [-90.1, 90.1])
def test_out_of_range_latitude_rejected_by_schema(bad_lat: float) -> None:
    with pytest.raises(ValidationError):
        _payload(latitude=bad_lat)


@pytest.mark.parametrize("bad_lon", [-180.1, 180.1])
def test_out_of_range_longitude_rejected_by_schema(bad_lon: float) -> None:
    with pytest.raises(ValidationError):
        _payload(longitude=bad_lon)


def test_negative_speed_rejected_by_schema() -> None:
    with pytest.raises(ValidationError):
        _payload(speed_mps=-1.0)


@pytest.mark.parametrize("bad_heading", [-1.0, 360.0])
def test_out_of_range_heading_rejected_by_schema(bad_heading: float) -> None:
    with pytest.raises(ValidationError):
        _payload(heading_deg=bad_heading)


def test_heading_none_is_accepted() -> None:
    assert _validate(_payload(heading_deg=None)) == []


def test_negative_accuracy_rejected_by_schema() -> None:
    with pytest.raises(ValidationError):
        _payload(accuracy_m=-1.0)


def test_missing_required_field_rejected_by_schema() -> None:
    with pytest.raises(ValidationError):
        TelemetryIngestRequest(
            timestamp=NOW, latitude=10.0, longitude=10.0, speed_mps=5.0, source="synthetic"
        )  # type: ignore[call-arg]


def test_invalid_source_rejected_by_schema() -> None:
    with pytest.raises(ValidationError):
        _payload(source="carrier_pigeon")
