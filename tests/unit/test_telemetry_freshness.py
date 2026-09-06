"""Unit tests for app.telemetry.freshness - pure ordering and freshness
classification logic, no database, no clock reads."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.telemetry.freshness import classify_freshness, is_newer

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


def test_first_ever_event_is_always_newer() -> None:
    assert is_newer(T0, None) is True


def test_later_timestamp_is_newer() -> None:
    assert is_newer(T0 + timedelta(seconds=1), T0) is True


def test_earlier_timestamp_is_not_newer() -> None:
    """The exact TASK-204 §4 example: 14:00:11 arriving after 14:00:12
    must not be treated as newer."""
    assert is_newer(T0 - timedelta(seconds=1), T0) is False


def test_identical_timestamp_is_not_newer() -> None:
    """A same-timestamp retry is a duplicate, not a new observation."""
    assert is_newer(T0, T0) is False


def test_freshness_within_stale_threshold_is_live() -> None:
    assert classify_freshness(0, stale_threshold_s=15, offline_threshold_s=300) == "live"
    assert classify_freshness(15, stale_threshold_s=15, offline_threshold_s=300) == "live"


def test_freshness_between_thresholds_is_stale() -> None:
    assert classify_freshness(16, stale_threshold_s=15, offline_threshold_s=300) == "stale"
    assert classify_freshness(300, stale_threshold_s=15, offline_threshold_s=300) == "stale"


def test_freshness_beyond_offline_threshold_is_offline() -> None:
    assert classify_freshness(301, stale_threshold_s=15, offline_threshold_s=300) == "offline"
