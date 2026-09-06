from __future__ import annotations

from app.ingestion.osm.tags import parse_direction, parse_lanes, parse_maxspeed_kph
from app.ingestion.osm.types import Direction


def test_parse_direction_defaults_to_both_when_untagged() -> None:
    assert parse_direction(None) == Direction.BOTH


def test_parse_direction_forward_values() -> None:
    for value in ("yes", "1", "true", "YES"):
        assert parse_direction(value) == Direction.FORWARD


def test_parse_direction_backward_values() -> None:
    for value in ("-1", "reverse"):
        assert parse_direction(value) == Direction.BACKWARD


def test_parse_direction_unknown_value_is_conservatively_both() -> None:
    for value in ("reversible", "alternating", "garbage"):
        assert parse_direction(value) == Direction.BOTH


def test_parse_maxspeed_plain_number_is_kph() -> None:
    assert parse_maxspeed_kph("50") == 50


def test_parse_maxspeed_explicit_kph() -> None:
    assert parse_maxspeed_kph("50 kph") == 50


def test_parse_maxspeed_mph_converted_to_kph() -> None:
    assert parse_maxspeed_kph("30 mph") == 48  # round(30 * 1.60934)


def test_parse_maxspeed_unparseable_returns_none() -> None:
    for value in ("none", "walk", "signals", None):
        assert parse_maxspeed_kph(value) is None


def test_parse_lanes_valid() -> None:
    assert parse_lanes("2") == 2


def test_parse_lanes_invalid_or_missing() -> None:
    assert parse_lanes(None) is None
    assert parse_lanes("many") is None
    assert parse_lanes("0") is None
    assert parse_lanes("-1") is None
