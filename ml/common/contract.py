"""The feature contract - see docs/architecture/TASK205_DESIGN.md §3.

A typed, explicit registry of every feature this foundation produces, in
place of an uncontrolled dictionary of arbitrary columns (TASK-205 §2's
explicit requirement). This is the reference documentation *and* the
thing `ml/common/dataset.py` writes columns for, `ml/common/cli.py`'s
`stats` command reports against, and any future `ml/<model>/features.py`
reads to know what's available - one source of truth, not three that can
drift apart.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class FeatureCategory(StrEnum):
    """TASK-205 §29's mandatory classification - never mix TARGET into
    the same bucket as an actual predictor column."""

    STATIC = "static"  # from canonical road-network schema, does not change
    TEMPORAL = "temporal"  # derived purely from the feature timestamp itself
    OBSERVED = "observed"  # a single raw telemetry reading, unaggregated
    DERIVED = "derived"  # an aggregate/computed function of one or more observations
    TARGET = "target"  # a future-facing label - never a feature, never fed to itself


@dataclass(frozen=True, slots=True)
class FeatureDefinition:
    name: str
    description: str
    dtype: str  # "float" | "int" | "bool" | "str" | "timestamp"
    unit: str | None
    source: str
    temporal_meaning: str
    category: FeatureCategory
    aggregation: str | None = None
    valid_range: tuple[float | None, float | None] | None = None
    missing_value_behavior: str = (
        "row omitted for this entity/timestamp when unavailable - never imputed " "(TASK-205 §26)"
    )
    leakage_risk: str = (
        "none - computed only from source rows with ts strictly before the feature "
        "timestamp T (TASK-205 §7)"
    )
    intended_use: str = "traffic speed prediction (doc 07 §7.1)"


FEATURE_SET_VERSION = "v1"

# The road_segment x timestamp grain (TASK-205 §1.A - traffic prediction).
# Column order here is the column order dataset.py writes.
ROAD_SEGMENT_FEATURE_CONTRACT: tuple[FeatureDefinition, ...] = (
    FeatureDefinition(
        name="road_segment_id",
        description="Canonical RoadSegment identity - the entity key for this grain.",
        dtype="uuid",
        unit=None,
        source="road_segments.id (TASK-201/202)",
        temporal_meaning="identity, not time-varying",
        category=FeatureCategory.STATIC,
        missing_value_behavior="never missing - the row's primary key",
        leakage_risk="none",
        intended_use="entity identity for all target families sharing this grain",
    ),
    FeatureDefinition(
        name="feature_ts",
        description="The feature row's canonical timestamp T (UTC). Every other "
        "column is computed from data with ts < T only.",
        dtype="timestamp",
        unit=None,
        source="dataset generator's bucket boundary (TASK-205 §6)",
        temporal_meaning="bucket upper bound, exclusive",
        category=FeatureCategory.STATIC,
        missing_value_behavior="never missing - the row's timestamp key",
        leakage_risk="none - defines the leakage boundary itself",
        intended_use="join key / leakage boundary for all target families",
    ),
    FeatureDefinition(
        name="length_m",
        description="Segment physical length.",
        dtype="float",
        unit="meters",
        source="road_segments.length_m (TASK-202)",
        temporal_meaning="static",
        category=FeatureCategory.STATIC,
        valid_range=(0.0, None),
        missing_value_behavior="null if the canonical row has no cached length",
    ),
    FeatureDefinition(
        name="road_class",
        description="OSM highway classification.",
        dtype="str",
        unit=None,
        source="road_segments.road_class (TASK-202)",
        temporal_meaning="static",
        category=FeatureCategory.STATIC,
        missing_value_behavior="null if unclassified",
    ),
    FeatureDefinition(
        name="lanes",
        description="Number of lanes.",
        dtype="int",
        unit="lanes",
        source="road_segments.lanes (TASK-202)",
        temporal_meaning="static",
        category=FeatureCategory.STATIC,
        valid_range=(1, None),
        missing_value_behavior="null if not tagged in OSM",
    ),
    FeatureDefinition(
        name="maxspeed_kph",
        description="Posted/legal speed limit.",
        dtype="float",
        unit="km/h",
        source="road_segments.maxspeed_kph (TASK-202)",
        temporal_meaning="static",
        category=FeatureCategory.STATIC,
        valid_range=(0.0, None),
        missing_value_behavior="null if not tagged in OSM",
    ),
    FeatureDefinition(
        name="is_oneway",
        description="Whether the segment is one-way.",
        dtype="bool",
        unit=None,
        source="road_segments.is_oneway (TASK-202)",
        temporal_meaning="static",
        category=FeatureCategory.STATIC,
        missing_value_behavior="never missing - NOT NULL in the canonical schema",
    ),
    FeatureDefinition(
        name="start_intersection_degree",
        description="Total degree (in+out directed edges) of the segment's start "
        "intersection in the TASK-203 canonical graph.",
        dtype="int",
        unit="edges",
        source="TASK-203 nx.MultiDiGraph, via app.graph.builder.build_road_graph",
        temporal_meaning="static (as of the graph build, itself derived from current "
        "PostGIS state)",
        category=FeatureCategory.STATIC,
        valid_range=(0, None),
        missing_value_behavior="null only if the intersection is absent from the built graph "
        "(should not happen for a valid canonical segment)",
        intended_use="junction-complexity proxy for traffic speed prediction",
    ),
    FeatureDefinition(
        name="end_intersection_degree",
        description="Total degree of the segment's end intersection in the "
        "TASK-203 canonical graph.",
        dtype="int",
        unit="edges",
        source="TASK-203 nx.MultiDiGraph, via app.graph.builder.build_road_graph",
        temporal_meaning="static (as of the graph build)",
        category=FeatureCategory.STATIC,
        valid_range=(0, None),
        missing_value_behavior="null only if the intersection is absent from the built graph",
        intended_use="junction-complexity proxy for traffic speed prediction",
    ),
    FeatureDefinition(
        name="hour_of_day",
        description="Hour of `feature_ts`, UTC.",
        dtype="int",
        unit=None,
        source="derived from feature_ts",
        temporal_meaning="instantaneous, at T",
        category=FeatureCategory.TEMPORAL,
        valid_range=(0, 23),
        missing_value_behavior="never missing",
        leakage_risk="none - derived from T itself, not any observation",
    ),
    FeatureDefinition(
        name="day_of_week",
        description="ISO day of week of `feature_ts`, UTC (0=Monday..6=Sunday).",
        dtype="int",
        unit=None,
        source="derived from feature_ts",
        temporal_meaning="instantaneous, at T",
        category=FeatureCategory.TEMPORAL,
        valid_range=(0, 6),
        missing_value_behavior="never missing",
        leakage_risk="none",
    ),
    FeatureDefinition(
        name="is_weekend",
        description="Whether `feature_ts` falls on Saturday or Sunday, UTC.",
        dtype="bool",
        unit=None,
        source="derived from feature_ts",
        temporal_meaning="instantaneous, at T",
        category=FeatureCategory.TEMPORAL,
        missing_value_behavior="never missing",
        leakage_risk="none",
    ),
    FeatureDefinition(
        name="is_peak",
        description="Whether `feature_ts` falls in a configured peak-hour window "
        "(TASK-205 §4 - default weekday 07:00-10:00 or 17:00-20:00 UTC).",
        dtype="bool",
        unit=None,
        source="derived from feature_ts + app.core.config peak-hour setting",
        temporal_meaning="instantaneous, at T",
        category=FeatureCategory.TEMPORAL,
        missing_value_behavior="never missing",
        leakage_risk="none",
    ),
    FeatureDefinition(
        name="speed_now_mps",
        description="Speed from the most recent telemetry observation on this "
        "segment strictly before T.",
        dtype="float",
        unit="m/s",
        source="telemetry.speed_mps (TASK-204)",
        temporal_meaning="last observation with ts < T",
        category=FeatureCategory.OBSERVED,
        valid_range=(0.0, 40.0),
        missing_value_behavior="null if no observation exists on this segment before T",
    ),
    FeatureDefinition(
        name="age_s",
        description="Seconds between T and the most recent observation's timestamp.",
        dtype="float",
        unit="seconds",
        source="derived: feature_ts - telemetry.ts",
        temporal_meaning="as of T",
        category=FeatureCategory.DERIVED,
        valid_range=(0.0, None),
        missing_value_behavior="null if speed_now_mps is null",
        intended_use="data-quality/confidence indicator (TASK-205 §14), not a predictor per se",
    ),
    FeatureDefinition(
        name="speed_mean_5m",
        description="Mean observed speed on this segment in the 5-minute window " "ending at T.",
        dtype="float",
        unit="m/s",
        source="telemetry.speed_mps (TASK-204)",
        temporal_meaning="window [T-300s, T)",
        category=FeatureCategory.DERIVED,
        aggregation="mean",
        valid_range=(0.0, 40.0),
        missing_value_behavior="null if zero observations fall in the window",
    ),
    FeatureDefinition(
        name="speed_mean_15m",
        description="Mean observed speed on this segment in the 15-minute window " "ending at T.",
        dtype="float",
        unit="m/s",
        source="telemetry.speed_mps (TASK-204)",
        temporal_meaning="window [T-900s, T)",
        category=FeatureCategory.DERIVED,
        aggregation="mean",
        valid_range=(0.0, 40.0),
        missing_value_behavior="null if zero observations fall in the window",
    ),
    FeatureDefinition(
        name="speed_std_15m",
        description="Sample standard deviation of observed speed on this segment "
        "in the 15-minute window ending at T.",
        dtype="float",
        unit="m/s",
        source="telemetry.speed_mps (TASK-204)",
        temporal_meaning="window [T-900s, T)",
        category=FeatureCategory.DERIVED,
        aggregation="stddev_samp",
        valid_range=(0.0, None),
        missing_value_behavior="null if fewer than 2 observations fall in the window "
        "(stddev of 1 sample is undefined, not zero)",
    ),
    FeatureDefinition(
        name="vehicle_count_5m",
        description="Distinct vehicles observed on this segment in the 5-minute "
        "window ending at T.",
        dtype="int",
        unit="vehicles",
        source="telemetry.vehicle_id (TASK-204)",
        temporal_meaning="window [T-300s, T)",
        category=FeatureCategory.DERIVED,
        aggregation="count distinct",
        valid_range=(0, None),
        missing_value_behavior="0 is a genuine, distinct-from-null observation here - "
        "an empty window count is not the same ambiguity as a missing speed reading "
        "(see TASK205_DESIGN.md §14)",
    ),
    FeatureDefinition(
        name="vehicle_count_15m",
        description="Distinct vehicles observed on this segment in the 15-minute "
        "window ending at T.",
        dtype="int",
        unit="vehicles",
        source="telemetry.vehicle_id (TASK-204)",
        temporal_meaning="window [T-900s, T)",
        category=FeatureCategory.DERIVED,
        aggregation="count distinct",
        valid_range=(0, None),
        missing_value_behavior="0 is a genuine count, not missing",
    ),
    FeatureDefinition(
        name="observation_count_15m",
        description="Total telemetry rows (not distinct vehicles) on this segment "
        "in the 15-minute window ending at T - the sample size backing every "
        "*_15m aggregate above.",
        dtype="int",
        unit="observations",
        source="telemetry (TASK-204)",
        temporal_meaning="window [T-900s, T)",
        category=FeatureCategory.DERIVED,
        aggregation="count",
        valid_range=(0, None),
        missing_value_behavior="0 is a genuine count, not missing",
        intended_use="data-quality/confidence indicator (TASK-205 §14) - lets a "
        "consumer distinguish 'genuinely low traffic' from 'we have one sample'",
    ),
)
