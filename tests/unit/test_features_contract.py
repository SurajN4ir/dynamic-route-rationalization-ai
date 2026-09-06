"""Unit tests for ml.common.contract - the feature contract's own
internal consistency (TASK-205 §2/§29): no duplicate names, no TARGET
category mixed into the feature contract, every field populated."""

from __future__ import annotations

from ml.common.contract import ROAD_SEGMENT_FEATURE_CONTRACT, FeatureCategory


def test_no_duplicate_feature_names() -> None:
    names = [f.name for f in ROAD_SEGMENT_FEATURE_CONTRACT]
    assert len(names) == len(set(names))


def test_no_target_category_in_feature_contract() -> None:
    """TASK-205 §29: never mix targets into feature columns."""
    categories = {f.category for f in ROAD_SEGMENT_FEATURE_CONTRACT}
    assert FeatureCategory.TARGET not in categories


def test_every_feature_has_required_metadata() -> None:
    for feature in ROAD_SEGMENT_FEATURE_CONTRACT:
        assert feature.name
        assert feature.description
        assert feature.dtype
        assert feature.source
        assert feature.temporal_meaning
        assert feature.category in FeatureCategory
        assert feature.missing_value_behavior
        assert feature.leakage_risk


def test_contract_covers_all_four_non_target_categories() -> None:
    categories = {f.category for f in ROAD_SEGMENT_FEATURE_CONTRACT}
    assert categories == {
        FeatureCategory.STATIC,
        FeatureCategory.TEMPORAL,
        FeatureCategory.OBSERVED,
        FeatureCategory.DERIVED,
    }


def test_road_segment_id_and_feature_ts_are_first_two_columns() -> None:
    """The entity key and leakage-boundary timestamp must be present and
    lead the column order for a readable, unambiguous dataset."""
    names = [f.name for f in ROAD_SEGMENT_FEATURE_CONTRACT]
    assert names[0] == "road_segment_id"
    assert names[1] == "feature_ts"
