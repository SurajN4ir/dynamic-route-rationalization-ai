"""Unit tests for ml.common.splitting.split_chronologically - TASK-205
§19. Pure function, no database."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ml.common.splitting import split_chronologically

START = datetime(2026, 1, 1, tzinfo=UTC)
END = datetime(2026, 1, 11, tzinfo=UTC)  # 10-day span


def test_split_is_contiguous_and_chronological() -> None:
    result = split_chronologically(START, END)

    assert result.train_start == START
    assert result.train_end == result.validation_start
    assert result.validation_end == result.test_start
    assert result.test_end == END


def test_default_split_proportions() -> None:
    result = split_chronologically(START, END)

    assert (result.train_end - result.train_start) == timedelta(days=7)
    assert (result.validation_end - result.validation_start) == timedelta(days=1.5)
    assert (result.test_end - result.test_start) == timedelta(days=1.5)


def test_custom_fractions_are_respected() -> None:
    result = split_chronologically(
        START, END, train_fraction=0.5, validation_fraction=0.25, test_fraction=0.25
    )

    assert (result.train_end - result.train_start) == timedelta(days=5)
    assert (result.validation_end - result.validation_start) == timedelta(days=2.5)


def test_fractions_not_summing_to_one_raises() -> None:
    with pytest.raises(ValueError, match="sum to 1.0"):
        split_chronologically(
            START, END, train_fraction=0.5, validation_fraction=0.5, test_fraction=0.5
        )


def test_end_before_start_raises() -> None:
    with pytest.raises(ValueError, match="end must be after start"):
        split_chronologically(END, START)


def test_naive_datetime_raises() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        split_chronologically(datetime(2026, 1, 1), datetime(2026, 1, 11))


def test_train_never_overlaps_validation_or_test() -> None:
    """The core anti-leakage property of chronological splitting: no
    timestamp belongs to two splits."""
    result = split_chronologically(START, END)

    assert result.train_end <= result.validation_start
    assert result.validation_end <= result.test_start
