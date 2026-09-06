# TASK-205 Design — Prediction Data & Feature Foundation

Companion to [PHASE2_DESIGN.md](PHASE2_DESIGN.md), [TASK202_DESIGN.md](TASK202_DESIGN.md),
[TASK203_DESIGN.md](TASK203_DESIGN.md), and [TASK204_DESIGN.md](TASK204_DESIGN.md).
Documents the decisions made building AURA's feature-generation
foundation - the layer between raw canonical/telemetry data and any
future ML model. **No model is trained or served here** (§23).

## 1. Architecture reconciliation

Read docs 01/02/03/04/05/06/07/10/12/13/14/15, TASK202-204_DESIGN.md,
ARCHITECTURE_REVIEW.md, plus the actual `Telemetry`/`RoadSegment`/
`Intersection`/`Route`/`RouteStop`/`Vehicle`/`VehicleAssignment` models,
the TASK-203 graph builder, and the full existing test suite.

**No blocking ambiguity** - every real discrepancy found was already
resolved by this task's own instructions (mirroring the TASK-202/204
pattern of documenting rather than stopping):

- **Where feature code lives.** doc 10 reserves `ml/<model>/features.py`
  per model; doc 07 §7.7 explicitly says "features are computed by
  shared functions in `ml/<model>/features.py`... revisit only if
  duplicated feature logic across models becomes a real maintenance
  problem." TASK-205 builds ONE shared foundation used by all five
  future model directories, so a new `ml/common/` package was added -
  not one of doc 10's reserved directories, flagged here the same way
  TASK-202 flagged its ingestion placement. `ml/traffic/`'s README
  ("Built starting Phase 4") is unchanged - per-model training code is
  still future work; only the shared data/feature layer exists now.
- **Storage decision.** doc 07 §7.7: "v1 does not require a dedicated
  feature-store product." `data/features/README.md` *already* states
  the intended shape: "DVC-tracked feature tables consumed by ml/
  training scripts." TASK-205 follows both: no new Postgres table, a
  CSV + JSON manifest written to `data/features/` (§16/§19).
- **ETA/Delay/Bunching targets need data that doesn't exist.** doc 04's
  `trips` table was never built (TASK-201 built `vehicle_assignments`
  instead - a standing assignment, not a specific timed journey), and no
  Route→RoadSegment ordered-path mapping exists anywhere in the schema
  (`routes.geometry` is a LineString, not a list of segment references).
  ETA needs "segments remaining to a stop"; Delay needs a scheduled-vs-
  actual instance; Bunching needs "vehicle order along a shared route
  path." All three are blocked on the same class of missing dependency.
  **Resolution:** conceptually defined (§11), generation explicitly
  marked deferred with the exact missing dependency named (§12) - never
  fabricated, per this task's own explicit instruction.
- **Demand target needs data that doesn't exist.** doc 04's
  `demand_observations` table was never created; no passenger-counting
  process exists anywhere in this project. **Resolution:** deferred,
  exactly matching this task's own worked example.
- **Test file naming collision.** `tests/unit/`/`tests/integration/`
  have no `__init__.py` (deliberate, per `pyproject.toml`'s mypy
  comment), so pytest requires globally-unique test file basenames
  across the whole tree - a real, mechanical discovery-time conflict
  when both a unit and an integration suite naturally want the name
  `test_features_targets.py`. **Resolution:** the integration file is
  named `test_features_target_generation.py` instead.
- **`ml/` needs to import `app.*` and be importable from tests.**
  Neither path was wired anywhere before this task (`ml/` has never held
  code). `pyproject.toml`'s `[tool.pytest.ini_options] pythonpath` gained
  `"."` (repo root) alongside the existing `"services/api"`, and
  `known-first-party` gained `"ml"` for import sorting - both purely
  additive, no existing path removed.

## 2. Prediction data architecture

```
canonical PostGIS (TASK-201/202) + TASK-203 graph + TASK-204 telemetry
                              |
                    ml/common (this task)
        static features | temporal features | telemetry-derived features
                              |
                      feature dataset (CSV + manifest)
                              |
                   future ml/<model>/ training (Phase 4+)
```

`ml/common/` never writes to Postgres and never mutates canonical data -
strictly a read-and-derive layer, same principle as TASK-203's graph and
TASK-204's segment association.

## 3. Feature grains (TASK-205 §1)

| Family | Grain | Status |
|---|---|---|
| A. Traffic | `road_segment x timestamp` | **implemented** (§4-8, this task's flagship) |
| B. ETA | vehicle/trip/segment observation x timestamp | conceptual only (§11/§12) |
| C. Delay | vehicle/route operational observation x timestamp | conceptual only |
| D. Demand | stop/route x timestamp | conceptual only |
| E. Bunching | vehicle pair/headway x timestamp | conceptual only |

Not forced into one universal row shape (per this task's own explicit
guidance) - each family's natural grain differs, and only one has both a
clean grain *and* real source data today.

## 4. Feature contract

`ml/common/contract.py:ROAD_SEGMENT_FEATURE_CONTRACT` - 21 typed
`FeatureDefinition` entries (name, description, dtype, unit, source,
temporal_meaning, category, aggregation, valid_range,
missing_value_behavior, leakage_risk, intended_use), one source of truth
also used by `ml/common/cli.py stats`/`validate`. `FeatureCategory`
(STATIC/TEMPORAL/OBSERVED/DERIVED/TARGET) enforces TASK-205 §29's
classification; `test_features_contract.py` asserts the feature contract
itself never contains a TARGET-category entry.

## 5. Static features

`ml/common/static_features.py`, bulk-loaded once per run: `length_m`,
`road_class`, `lanes`, `maxspeed_kph`, `is_oneway` (direct `RoadSegment`
column passthrough) plus `start_intersection_degree`/
`end_intersection_degree` - computed by reusing TASK-203's already-built
`nx.MultiDiGraph` (`app.graph.builder.build_road_graph`), not a
re-derivation via raw SQL. This is exactly the "use the graph for
computational lookup where appropriate" TASK-204's design doc already
anticipated for a future consumer.

## 6. Telemetry-derived features

`ml/common/telemetry_features.py`: `speed_now_mps`/`age_s` (latest
observation strictly before T), `speed_mean_5m`, `speed_mean_15m`,
`speed_std_15m`, `vehicle_count_5m`, `vehicle_count_15m`,
`observation_count_15m`. Two windows only (5/15 min), matching doc 01's
shortest traffic horizons and TASK-204's already-established stale/
offline thresholds - not an arbitrary sweep (§8 below).

## 7. Temporal features

`ml/common/time_features.py`, UTC-only: `hour_of_day`, `day_of_week`
(ISO, Monday=0), `is_weekend`, `is_peak` (default weekday 07:00-10:00 /
17:00-20:00 UTC, overridable). **UTC, not "configured local operational
time"** - `Settings` has no timezone field anywhere in this codebase, and
every existing `timestamptz` column (TASK-201-204) is already handled as
UTC throughout; inventing a local-time convention now would be exactly
the silently-assumed architecture this project's process forbids.
`compute_temporal_features` raises on a naive timestamp rather than
guessing, matching TASK-204's own validation precedent.

## 8. Temporal alignment (leakage boundary)

A feature row's canonical timestamp T is a **fixed bucket's exclusive
upper bound**: `_bucket_timestamps` generates `start+bucket_s,
start+2*bucket_s, ..., <= end` (`ml/common/dataset.py`). Every windowed
query is `[T-window_s, T)` - inclusive start, **exclusive end** - so an
observation timestamped exactly at T is never visible to that row
(`tests/integration/test_feature_leakage.py::test_observation_exactly_at_t_is_excluded`
proves this directly). A road segment with zero observations in the
largest (15-min) window at a given T is **omitted from the dataset
entirely for that bucket** - not emitted as a row of nulls - the single
row-emission gate for the whole generator (§14 below explains why).

## 9. Leakage-prevention strategy

Every query in `telemetry_features.py`/`targets.py` is filtered on the
`ts` column directly (`< feature_ts` for features, `>= window_start` for
targets) - there is no code path that reads telemetry without an
explicit, testable timestamp bound. `tests/integration/test_feature_leakage.py`
(8 tests) proves: an observation at exactly T is excluded; one
microsecond before T is included; a future spike never contaminates
`speed_now`/window means/counts; the full dataset generator (not just the
unit-level query) never leaks; the inverse direction (a target never
picks up the pre-T "current" observation instead of a genuinely future
one); both feature-window boundaries (`[T-900s, T)`) are exact; and one
comprehensive 9-point boundary partition
(`test_full_boundary_partition_features_vs_target`) that places a
distinct, identifiable speed value at every interesting timestamp around
both T and T+H (`T-ε, T, T+ε, T+H-ε, T+H, T+H+ε, T+H+W-ε, T+H+W,
T+H+W+ε`) and asserts, by exact value, precisely which ones feed
features, which feed the target, and which feed neither - added during
architectural review specifically to leave no boundary behavior to
infer.

## 10. Feature windows

5-minute and 15-minute only (`WINDOW_SHORT_S`/`WINDOW_LONG_S` in
`telemetry_features.py`) - deliberately small. Justification: matches
doc 01 FR-PRED-01's two shortest traffic horizons (5/15/30/60 min) and
TASK-204's already-established `telemetry_stale_threshold_s`(15s)/
`telemetry_offline_threshold_s`(300s) convention; a wider sweep (30m,
60m, ...) is explicitly deferred rather than built speculatively (§8's
"avoid unnecessary feature explosion").

## 11. Target definitions

`ml/common/targets.py:TARGET_DEFINITIONS` - all five families
(entity, target_calculation, required_source_data, units,
missing_data_behavior, availability, unavailable_reason) per §9 of this
task's brief. Only `traffic_speed` is `AVAILABLE`; the other four are
`DEFERRED`, each with an explicit, specific `unavailable_reason` (not a
generic "not implemented") - `tests/unit/test_features_targets.py`
enforces that every deferred target actually states one.

### 11a. Target semantics — exact timestamp boundaries (architectural review addendum)

The traffic target is a **future window average**, not a single future
point sample - explicitly a window aggregate, chosen for the same reason
the feature side aggregates over windows rather than trusting one noisy
instantaneous reading (methodological symmetry between X(T) and y(T+H),
not an arbitrary difference in how each side is computed). For feature
timestamp T and horizon H (`horizon_s`, one of `TARGET_HORIZONS_S`):

```
FEATURES:  every value in ROAD_SEGMENT_FEATURE_CONTRACT is computed
           from telemetry with ts < T                    (strict)

TARGET:    target_traffic_speed_mps_h<H> = mean(speed_mps)
           over telemetry with
               T + H <= ts < T + H + TARGET_WINDOW_S      (TARGET_WINDOW_S = 300s)
```

Both boundaries are exact and enforced by the query itself (`ml/common/
targets.py:generate_traffic_target`), not by convention: `ts >=
window_start` (inclusive start) and `ts < window_end` (exclusive end),
mirroring the feature side's own inclusive-start/exclusive-end window
convention (§10). Because every configured horizon is >= 300s,
`window_start = T + H` is always strictly greater than T - there is no
timestamp that could simultaneously satisfy `ts < T` (feature-eligible)
and `T+H <= ts` (target-eligible); the two sets are disjoint by
construction, not merely by convention. `TARGET_WINDOW_S` is a named
module constant (not a literal buried in the query), referenced by both
the code and the manifest (§17a) so the two can never drift apart.

`tests/integration/test_feature_leakage.py::test_full_boundary_partition_features_vs_target`
proves this exhaustively: nine telemetry rows, one at each of
`T-ε, T, T+ε, T+H-ε, T+H, T+H+ε, T+H+W-ε, T+H+W, T+H+W+ε` (ε = 1
microsecond, W = `TARGET_WINDOW_S`), each carrying a distinct speed value
so the resulting feature/target values pin down *exactly* which points
were used - not merely that leakage didn't happen to occur.

## 12. Target horizons

`+5 min` and `+15 min` (`TARGET_HORIZONS_S = (300, 900)`) - matching this
task's §10 examples and doc 01's two shortest traffic horizons. `+30min`/
`+60min` are deliberately deferred to a later task once more historical
telemetry volume exists to make longer horizons meaningful - adding them
is a one-line change to `TARGET_HORIZONS_S`/the CLI's `--horizons` flag,
not a redesign.

## 13. Data availability

**Available now:** road network (`intersections`/`roads`/`road_segments`,
TASK-201/202), the TASK-203 graph, `telemetry` (TASK-204),
`vehicle_assignments` (TASK-201), all UTC timestamps.

**Required later:** passenger-count observations (`demand_observations`
was never built) for Demand; a `trips`-equivalent journey instance with a
concrete scheduled time for Delay; a Route↔RoadSegment ordered-path
mapping for ETA and Bunching; incident data (`incidents` was never built)
for any future incident-aware feature; weather (never planned as a data
source in this codebase); external traffic observations (none exist,
₹0-architecture principle rules out a paid source).

## 14. Data-quality rules

**Four distinct "why is this missing" cases (architectural review
addendum) - never silently collapsed into one meaning:**

| Case | Meaning | How it manifests |
|---|---|---|
| A. Insufficient historical feature data | Fewer than 1 observation in the 15-min window *before* T | The (segment, T) row is **absent from the dataset entirely** - the row-eligibility gate (§8/§17a) |
| B. Missing future target data | Zero observations in `[T+H, T+H+W)` | The **row is present** (features were fine); its `target_traffic_speed_mps_h<H>` cell is empty/`null` - never `0.0` |
| C. Invalid telemetry | Bad coordinates/speed/timestamp | Never reaches `telemetry` at all - rejected by TASK-204 ingestion validation before this layer ever runs |
| D. No observations for the entity, ever | Same manifestation as A | Also an absent row - A and D are indistinguishable at the row level by design, since both mean "no feature basis exists," and a consumer doesn't need to know *why* there's no basis, only that there isn't one |

Case A/D (row absent) and case B (row present, target cell empty) are
**structurally different outcomes** - a present row with an empty target
is exactly as usable for feature-only analysis as one with a target, and
must never be pruned automatically; only a downstream training step that
specifically needs labeled rows should filter on the target columns being
non-empty, and that filtering decision belongs to that step, not to
dataset generation. `test_row_is_present_with_missing_target_when_no_future_data_exists`
proves the row survives when every configured horizon's target is
unavailable.

- **Sparse observations:** a segment/bucket combination with zero
  observations in the 15-minute window is omitted from the dataset
  entirely (§8) - never a null-filled row.
- **Insufficient sample for std:** `speed_std_15m` is `null` (not `0.0`)
  when fewer than 2 observations exist in the window - the standard
  deviation of one sample is undefined, not zero
  (`test_speed_std_requires_at_least_two_samples`).
- **Duplicate/out-of-order/stale telemetry:** already handled at the
  source by TASK-204's ingestion pipeline before a row ever reaches
  `telemetry` - this layer trusts that guarantee rather than
  re-validating it.
- **Segment association failures:** a `telemetry` row with
  `road_segment_id IS NULL` (TASK-204's "no segment within radius" case)
  simply never contributes to any segment's aggregate - no special
  handling needed, the `GROUP BY road_segment_id` naturally excludes it.
- **Impossible speeds/invalid coordinates:** rejected at TASK-204
  ingestion time (`telemetry_max_speed_mps`, coordinate range
  validation) - never reach this layer.

## 15. Missing-data policy

Never zero-fill. `vehicle_count_5m`/`vehicle_count_15m`/
`observation_count_15m` are the one deliberate exception - `COUNT(...)`
over an empty set is genuinely `0`, a real, meaningful value ("we looked
and saw nothing"), categorically different from `speed_mean_5m` being
`null` ("we have no basis to compute a mean at all"). Every other numeric
feature is `null`/omitted when its source data doesn't exist, per this
task's explicit "no telemetry does not mean speed=0" example.

## 16. Feature versioning

`ml/common/contract.py:FEATURE_SET_VERSION = "v1"`, written into every
generated dataset's `manifest.json`. A future breaking change to the
feature contract bumps this string; a training dataset's manifest always
says exactly which version produced it - lightweight, no feature
registry service.

## 17. Dataset generation

`ml/common/dataset.py:generate_road_segment_dataset(session, config)`
where `DatasetGenerationConfig` takes `start`, `end`, `bucket_s` (default
300s), `horizons_s` (default `(300, 900)`) - time range, grain (fixed to
road_segment for now), feature-set version (implicit via the contract
module imported), and horizon are all generator parameters, never
hardcoded to one period. `write_dataset` writes `dataset.csv` +
`manifest.json` to a caller-given directory, default
`data/features/road_segment_traffic_v1`.
Deterministic: `test_generation_is_deterministic` generates the same
dataset twice from unchanged data and asserts byte-for-byte row equality.

### 17a. Manifest fields (architectural review addendum)

Added during review so the dataset artifact is self-documenting - a
consumer should never need to go find source comments to understand what
they're looking at:

| Field | Content |
|---|---|
| `feature_set_version`, `grain`, `generated_at`, `range_start`/`range_end`, `bucket_s`, `horizons_s`, `row_count`, `entity_count`, `columns` | as before |
| `feature_window_s` | `{"short": 300, "long": 900}` - the exact windows §10 describes |
| `target_window_s` | `300` - `TARGET_WINDOW_S`, the same value the target query actually uses (§11a) |
| `row_eligibility_rule` | full prose statement of the row-omission gate (§8/§17b) - literally embedded, not just documented in this file |
| `target_definition` | full prose statement of the exact target window semantics (§11a) and its missing-value behavior |

## 17b. Telemetry selection bias (architectural review addendum)

"A segment with zero observations in the 15-minute window is omitted" is
a **deliberate training-data eligibility rule**, not an incidental
side-effect - it is now:

1. **Documented explicitly** here and in `ml/common/dataset.py`'s
   `ROW_ELIGIBILITY_RULE` module constant.
2. **Exposed in the manifest** (§17a) as `row_eligibility_rule`, so a
   future evaluation script can read it back without re-deriving it from
   source.
3. **Named for what it implies**: the dataset represents *observed*
   segments at *observed* times, not a complete grid of the whole network
   at every timestamp. A future model trained on it should not assume an
   absent (segment, T) combination means "no traffic" - it means "we
   don't have enough recent history to say anything," which is a
   materially different claim. This is exactly the distinction TASK-205
   §14/§26 already required for missing *values*; the review extended it
   explicitly to missing *rows*.

## 18. Train/validation/test methodology

`ml/common/splitting.py:split_chronologically(start, end, ...)` -
earliest period trains, next validates, latest tests, **never** a random
row split. Documented rationale (also in the module docstring): random
splitting on time-series transportation data lets a model train on
observations from *after* a validation-set timestamp for the same
segment, leaking future information at the dataset-split level even if
every individual feature row is leakage-clean. Default 70/15/15,
overridable - not hardcoded, since the right split depends on how much
historical span actually exists once real data accumulates.

## 19. Online/offline feature parity

Every feature in `ROAD_SEGMENT_FEATURE_CONTRACT` is computed from
`telemetry`/`road_segments`/the TASK-203 graph using only bounded,
recent-window queries (`ts < T`, `[T-900s, T)`) - nothing here reads a
training-only historical aggregate that couldn't equally be computed at
serving time for a live T="now". No offline-only feature was introduced
in this task. `ml/common/telemetry_features.py`/`static_features.py`
would be called identically by a future online inference path - the
functions don't know or care whether T is in the past or is "now."

## 20. Storage decision

No new Postgres table (§1's reconciliation). A dataset is a directory
containing `dataset.csv` (typed columns, one per `FeatureDefinition`,
matching this task's explicit "typed columns preferred over a generic
JSON blob" instruction) + `manifest.json` (reproducibility metadata).
Plain stdlib `csv`/`json` - no pandas/pyarrow dependency added, since SQL
aggregation already does the heavy numeric work and the resulting row
count at this project's scale (doc 02.2: <=100 vehicles) doesn't warrant
a dataframe library.

## 21. CLI/API boundary

No public API - TASK-205 does not serve predictions. `python -m
ml.common.cli {generate,stats,validate}` (see `ml/common/cli.py`),
following `app.ingestion.cli`/`app.graph.cli`'s established single-
`asyncio.run()`/`dispose_engine()` pattern for the DB-touching `generate`
command; `stats`/`validate` are pure file I/O and run synchronously.

## 22. Testing

- **Unit** (31 tests, no database): temporal feature computation
  (peak-window boundaries, weekend detection, naive-timestamp rejection),
  feature-contract self-consistency (no duplicate names, no TARGET
  category, required metadata present), target-definition metadata
  (exactly one `AVAILABLE` family, every `DEFERRED` one states why),
  chronological splitting (contiguity, custom fractions, non-summing
  rejection, naive-datetime rejection), and dataset-stats computation
  (missingness, target availability, min/max/mean) against synthetic
  CSVs.
- **Integration** (30 tests, real PostGIS): static-feature passthrough
  and graph-derived degree (junction vs. dead-end), telemetry-derived
  window aggregation (5m/15m distinction, distinct-vehicle counting,
  std sample-size guard, per-segment independence), the traffic target
  generator (future-window averaging, horizon distinction), end-to-end
  dataset generation (row shape, multi-bucket iteration, target columns,
  determinism, CSV/manifest writing, zero-telemetry case, the missing-
  target-row case, manifest self-documentation), and 8 explicit leakage
  tests (§9), including the exhaustive 9-point boundary partition added
  during architectural review.
- **Regression**: all 187 pre-existing TASK-201-204 tests still pass
  unmodified.

## 23. Explicit confirmation: no ML model

`ml/common/` contains zero references to any training library
(scikit-learn, XGBoost, LightGBM, PyTorch, TensorFlow), no `.fit()`/
`.predict()` call, no hyperparameter search, no model artifact, no
MLflow/DVC experiment run, no prediction-serving code path. The only
"prediction" content is `TARGET_DEFINITIONS`' metadata (English-language
descriptions of what a future model would predict) and one deterministic
SQL-aggregation label generator for the traffic family - neither trains
or evaluates anything.

## 24. Known limitations

- Only the traffic family has a working end-to-end pipeline; ETA/Delay/
  Demand/Bunching are metadata-only until their named missing
  dependencies are built.
- No historical telemetry volume exists yet to generate a genuinely
  useful training dataset - the generator is correct and tested, but a
  real multi-day/multi-week synthetic or SUMO-driven telemetry run is
  separate, later work.
- Row-emission is gated on the 15-minute window specifically; a segment
  with an observation 20 minutes old and nothing more recent produces no
  row at all, even though a "stale but present" signal might be useful
  to a future model - a deliberate simplicity/consistency tradeoff (§8),
  revisit if a future model wants that signal explicitly.
- `GET`-style bulk loading of static features re-runs the full TASK-203
  graph build once per `generate` invocation - fine at this project's
  scale, would need caching if datasets were generated far more
  frequently.
- CSV output has no compression/columnar format; acceptable at current
  data volumes, revisit (e.g. Parquet via a new dependency) if dataset
  sizes grow substantially.

---
*v1.1 — TASK-205 baseline, plus the architectural review's target-
semantics addendum (§11a exact timestamp boundaries, §17a manifest
fields, §17b selection-bias documentation, §14's four-case missing-data
classification, and the 9-point boundary-partition leakage test).*
