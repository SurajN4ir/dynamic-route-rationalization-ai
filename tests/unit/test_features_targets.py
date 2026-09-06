"""Unit tests for ml.common.targets' metadata - TASK-205 §9/§11/§12's
"define targets without fabricating data" requirement, checked
structurally: every deferred target must explain why, and only the one
family with real source data today is marked available."""

from __future__ import annotations

from ml.common.targets import TARGET_DEFINITIONS, TargetAvailability


def test_all_five_prediction_families_are_defined() -> None:
    names = {t.name for t in TARGET_DEFINITIONS}
    assert names == {"traffic_speed", "eta", "delay", "demand", "bunching"}


def test_only_traffic_is_available_today() -> None:
    available = [
        t.name for t in TARGET_DEFINITIONS if t.availability == TargetAvailability.AVAILABLE
    ]
    assert available == ["traffic_speed"]


def test_every_deferred_target_states_its_unavailable_reason() -> None:
    for target in TARGET_DEFINITIONS:
        if target.availability == TargetAvailability.DEFERRED:
            assert target.unavailable_reason, f"{target.name} is deferred but gives no reason"


def test_available_target_has_no_dangling_unavailable_reason() -> None:
    traffic = next(t for t in TARGET_DEFINITIONS if t.name == "traffic_speed")
    assert traffic.unavailable_reason is None


def test_every_target_has_required_metadata() -> None:
    for target in TARGET_DEFINITIONS:
        assert target.entity
        assert target.target_calculation
        assert target.required_source_data
        assert target.units
        assert target.missing_data_behavior
