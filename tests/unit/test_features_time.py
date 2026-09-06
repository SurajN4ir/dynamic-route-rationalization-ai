"""Unit tests for ml.common.time_features - pure temporal feature
computation, no database, no clock reads."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ml.common.time_features import compute_temporal_features


def test_monday_morning_is_peak() -> None:
    ts = datetime(2026, 1, 5, 8, 0, 0, tzinfo=UTC)  # Monday
    result = compute_temporal_features(ts)
    assert result.day_of_week == 0
    assert result.is_weekend is False
    assert result.is_peak is True


def test_saturday_is_weekend_and_never_peak() -> None:
    ts = datetime(2026, 1, 10, 8, 0, 0, tzinfo=UTC)  # Saturday
    result = compute_temporal_features(ts)
    assert result.day_of_week == 5
    assert result.is_weekend is True
    assert result.is_peak is False


def test_sunday_is_weekend() -> None:
    ts = datetime(2026, 1, 11, 12, 0, 0, tzinfo=UTC)  # Sunday
    result = compute_temporal_features(ts)
    assert result.day_of_week == 6
    assert result.is_weekend is True


def test_midday_weekday_is_not_peak() -> None:
    ts = datetime(2026, 1, 5, 13, 0, 0, tzinfo=UTC)
    result = compute_temporal_features(ts)
    assert result.is_peak is False


def test_evening_peak_window() -> None:
    ts = datetime(2026, 1, 5, 18, 30, 0, tzinfo=UTC)
    result = compute_temporal_features(ts)
    assert result.is_peak is True


def test_peak_window_upper_bound_is_exclusive() -> None:
    ts = datetime(2026, 1, 5, 10, 0, 0, tzinfo=UTC)  # exactly 10:00, window is [7,10)
    result = compute_temporal_features(ts)
    assert result.is_peak is False


def test_hour_of_day_matches_timestamp() -> None:
    ts = datetime(2026, 1, 5, 23, 45, 0, tzinfo=UTC)
    result = compute_temporal_features(ts)
    assert result.hour_of_day == 23


def test_naive_timestamp_raises() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        compute_temporal_features(datetime(2026, 1, 5, 8, 0, 0))


def test_custom_peak_windows_override_default() -> None:
    ts = datetime(2026, 1, 5, 22, 0, 0, tzinfo=UTC)
    result = compute_temporal_features(ts, peak_hour_windows=((22, 23),))
    assert result.is_peak is True
