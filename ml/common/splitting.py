"""Chronological dataset splitting - see docs/architecture/TASK205_DESIGN.md
§19.

Time-series transportation data must never be split randomly by row: a
random split lets a model train on observations from *after* a
validation-set timestamp for the same segment, which leaks exactly the
kind of future information §7's leakage rules exist to prevent, just at
the dataset-split level instead of the per-row feature level. The correct
split is chronological - earliest period trains, next validates, latest
tests - so validation/test performance reflects genuinely forecasting
the future, not interpolating within an already-seen time range.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

DEFAULT_TRAIN_FRACTION = 0.7
DEFAULT_VALIDATION_FRACTION = 0.15
DEFAULT_TEST_FRACTION = 0.15


@dataclass(frozen=True, slots=True)
class ChronologicalSplit:
    train_start: datetime
    train_end: datetime
    validation_start: datetime
    validation_end: datetime
    test_start: datetime
    test_end: datetime


def split_chronologically(
    start: datetime,
    end: datetime,
    *,
    train_fraction: float = DEFAULT_TRAIN_FRACTION,
    validation_fraction: float = DEFAULT_VALIDATION_FRACTION,
    test_fraction: float = DEFAULT_TEST_FRACTION,
) -> ChronologicalSplit:
    """Splits `[start, end)` into three contiguous, non-overlapping,
    chronologically-ordered sub-ranges. Fractions must sum to 1.0 - a
    documented default (70/15/15), not a hardcoded one; override for a
    dataset whose actual historical span calls for a different split
    (TASK-205 §19)."""
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("split_chronologically requires timezone-aware bounds")
    if end <= start:
        raise ValueError("end must be after start")
    total = train_fraction + validation_fraction + test_fraction
    if abs(total - 1.0) > 1e-9:
        raise ValueError(f"train/validation/test fractions must sum to 1.0, got {total}")

    span = end - start
    train_end = start + span * train_fraction
    validation_end = train_end + span * validation_fraction

    return ChronologicalSplit(
        train_start=start,
        train_end=train_end,
        validation_start=train_end,
        validation_end=validation_end,
        test_start=validation_end,
        test_end=end,
    )
