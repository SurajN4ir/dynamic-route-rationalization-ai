# TASK-202 Design — OSM Road-Network Ingestion

Companion to [PHASE2_DESIGN.md](PHASE2_DESIGN.md) (TASK-201). Documents
the decisions made building the OSM ingestion pipeline, including one
architecture reconciliation finding that required a schema correction
before ingestion could be built correctly.

## 1. Architecture reconciliation finding (fixed before implementation)

PHASE2_DESIGN.md §4 already specified that a single OSM way could split
into multiple `RoadSegment` rows "at intersections if the way passes
through nodes shared with other ways" - but the schema TASK-201 actually
committed (migration `0002`) gave `road_segments` a bare single-column
`UNIQUE` constraint on `osm_way_id`. Those two statements are inconsistent:
if a way splits into N segments, N rows would all share the same
`osm_way_id`, which the committed constraint would reject outright.

This is not a values judgment with multiple reasonable answers (unlike
TASK-201's VehicleAssignment-vs-trips question, which was put to the
architect) - the task's own requirements (§5: "do not flatten all OSM ways
into one simplistic table"; §6: "suitable for future graph construction")
make correct way-splitting a hard requirement, and there is one correct
fix: the segment's stable OSM-derived identity is the *pair*
`(osm_way_id, way_seq)`, not `osm_way_id` alone. **Migration `0003`**
applies this fix:

- `road_segments.way_seq` (integer, nullable - null for manually-created
  segments with no parent way) added.
- `uq_road_segments_osm_way_id` (single-column) dropped, replaced with
  `uq_road_segments_osm_way_id_way_seq` (composite). Postgres unique
  constraints don't conflict on NULL, so this is a pure widening for
  non-OSM rows, not a behavior change.
- `road_segments.access`, `.maxspeed_kph`, `.lanes` added - informational
  columns for the OSM feature policy below (§3).
- `roads` gets a `(source, name)` unique constraint, needed for idempotent
  Road upserts when grouping same-named ways (§5).

See [`services/api/alembic/versions/0003_osm_ingestion_schema_fix.py`](../../services/api/alembic/versions/0003_osm_ingestion_schema_fix.py)
for the exact DDL, and doc 04 is *not* updated for this fix (0003 is
TASK-202's own migration, not a TASK-201 schema correction retroactively
rewritten into doc 04 - see §10 below for what *is* touched).

## 2. OSM → AURA mapping

| OSM source field | Transformation | AURA canonical field |
|---|---|---|
| `<node id lat lon>` | 1:1, kept only if the node qualifies as an intersection (§6) | `intersections.osm_node_id`, `.location` |
| `<way id>` | kept only if `highway` tag is supported (§3); may produce 1+ canonical rows (§5) | `road_segments.osm_way_id`, `.way_seq` |
| `way.tag[highway]` | passthrough | `road_segments.road_class`, `roads.road_class` |
| `way.tag[name]` | ways sharing the same name are grouped under one `Road` row (§5) | `roads.name` |
| `way.tag[oneway]` | normalized to `Direction.FORWARD/BACKWARD/BOTH` (§7) | `road_segments.is_oneway` + start/end intersection order |
| `way.tag[maxspeed]` | parsed, mph converted to km/h | `road_segments.maxspeed_kph` |
| `way.tag[lanes]` | parsed as integer | `road_segments.lanes` |
| `way.tag[access]` | raw passthrough, not filtered on | `road_segments.access` |
| way's node list geometry | built into a LineString from member node coordinates, split at intersection nodes | `road_segments.geometry` |
| (derived) | `ST_Length`-equivalent estimate on the built geometry | `road_segments.length_m` |

Everything else on an OSM way or node is dropped - this is the "controlled
supported-tag policy" §3 defines, not an omission.

## 3. Supported OSM feature/tag policy

**Highway values accepted** (`app/ingestion/osm/tags.py:SUPPORTED_HIGHWAY_VALUES`):
`motorway, trunk, primary, secondary, tertiary, unclassified, residential,
living_street`, plus their `_link` variants. Excludes `footway`, `cycleway`,
`path`, `steps`, `pedestrian`, `track`, `service`, `construction`,
`proposed`, and anything else - this is the public, motor-vehicle-drivable
road set (matches the common "drivable network" convention, e.g. what
osmnx's default `drive` network type covers), not a lane-level or
multi-modal model. A way missing a `highway` tag entirely, or one with an
unsupported value, is rejected (not an error - a normal, counted outcome).

**Tags read**: `highway`, `name`, `oneway`, `maxspeed`, `lanes`, `access`.
No other tag has any effect. Unknown/unrecognized tags are silently
ignored - only a *missing or unsupported* `highway` tag, too few node
references, or an unresolvable node reference cause rejection (§4).

## 4. Rejection reasons (`app/ingestion/osm/types.py:RejectionReason`)

| Reason | Cause |
|---|---|
| `no_highway_tag` | way has no `highway` tag at all |
| `unsupported_highway_value` | `highway` present but not in the supported set |
| `too_few_nodes` | fewer than 2 node references (degenerate) |
| `unresolved_node_reference` | references a node id absent from the same extract |
| `duplicate_way_id` | the same way id appears twice in one source file |
| `invalid_geometry` | built geometry is degenerate (zero-length) or otherwise invalid - checked right before persistence, not earlier, since it depends on the *split* geometry, not the raw way |

None of these abort the whole run - they're recorded in `IngestionStats`
and logged, and ingestion continues with the remaining features.

## 5. Road vs RoadSegment transformation

- **RoadSegment** (the routable unit) = one edge between two canonical
  Intersections. A single OSM way produces **one RoadSegment per pair of
  consecutive intersection nodes** along its node list (§6) - `way_seq` is
  that split's 0-based index within the parent way.
- **Road** (optional, human-meaningful grouping) = ways sharing the same
  `name` tag, scoped to `source='osm'`. A way with no `name` tag produces
  segments with `road_id = NULL` - never forced into a placeholder Road.

**Known limitation:** grouping by bare name string can over-merge two
geographically disjoint roads that happen to share a name within one
extract (e.g. two unrelated "Main Street"s). Acceptable for a bounded,
small-extract, ₹0/dev-fixture scope; a future refinement could scope
grouping by spatial proximity or OSM `type=associatedStreet` relations.

## 6. Intersection derivation

A node qualifies as a canonical `Intersection` (`app/ingestion/osm/topology.py`)
if it is:
- the first or last node of **any** eligible way (every segment needs an
  endpoint, even a dead end with nothing else touching it), **or**
- referenced by **two or more distinct** eligible ways (a real topological
  junction).

A node referenced by only one way, at a non-endpoint position, is a shape
point - it contributes to that segment's geometry but is not itself an
Intersection row. This deliberately avoids "full lane-level modeling"
(TASK-202 §6's own caution) while remaining sufficient for a future
routing graph: every place a route could plausibly turn is a vertex,
nothing else is.

## 7. Directionality

`app/ingestion/osm/tags.py:parse_direction` + `app/ingestion/osm/topology.py`:

| OSM `oneway` value | Normalized `Direction` | Canonical effect |
|---|---|---|
| unset, `no`, `false` | `BOTH` | `is_oneway=False`; start/end follow the way's own node order (arbitrary but deterministic) |
| `yes`, `1`, `true` | `FORWARD` | `is_oneway=True`; start/end follow the way's own node order |
| `-1`, `reverse` | `BACKWARD` | `is_oneway=True`; the sub-path's node order is **reversed** before being split into start/end, so `start_intersection_id -> end_intersection_id` always represents the allowed travel direction regardless of which way OSM happened to draw the way |
| `reversible`, `alternating`, anything else unrecognized | `BOTH` (conservative) | treated as unrestricted |

**Known limitation:** time-dependent direction restrictions
(`reversible`/`alternating` lanes) are not modeled - deliberately, since
encoding time-of-day rules is out of scope for a topology-ingestion task
and no consumer needs it yet.

## 8. Source provenance & idempotency strategy

Every OSM-derived row is upserted, never blind-inserted, keyed by:

| Table | Idempotency key |
|---|---|
| `intersections` | `osm_node_id` |
| `roads` | `(source, name)` |
| `road_segments` | `(osm_way_id, way_seq)` |

Re-running ingestion against the *same* extract produces the *same* row
set (`skipped_duplicates` increments, nothing new is created). Re-running
against a *changed* extract (a tag value changed) updates the existing row
in place - `app/ingestion/osm/pipeline.py`'s resolvers always compare the
existing row's mutable fields against the new candidate and only write
when something actually differs, so a genuinely-unchanged re-run performs
zero writes, not just zero *new rows*. Verified against a live database,
not just asserted (see test summary, §14 of the implementation report).

The CLI's `--source` option is a **run-level label for stats/logging
only** (doc TASK-202 §17's "understand ... source"), not the DB `source`
enum column - that column is a fixed provenance *type*
(`'osm'`/`'manual'`, per doc 04's existing convention), not a free-text
per-run identifier, and the schema's `CHECK` constraint would reject an
arbitrary value there anyway. This is a deliberate distinction, not an
oversight.

## 9. Transaction strategy

`ingest_osm_file()` does not own the transaction boundary - it performs
its work (`session.add()`/`session.flush()`) on the session it's given,
and the **caller** commits or rolls back. The CLI (`app/ingestion/cli.py`)
commits only after the whole pipeline returns successfully, and rolls back
on any exception (`OSMParseError` or otherwise) - verified with a test
that forces a failure partway through segment persistence and confirms
zero rows survive. One transaction for the whole run, not per-road or
per-segment: correctness over throughput for this initial implementation
(TASK-202 §12/§16), acceptable at the bounded, small-extract scale this
task targets. A future large-dataset ingestion could chunk into several
transactions if needed - not required here.

## 10. Dry-run behavior

Dry-run is not a separate/fake code path. Every resolver
(`_resolve_intersection`/`_resolve_road`/`_resolve_segment` in
`pipeline.py`) always performs its real, read-only lookup and diff check
in both modes; it only skips the `session.add()`/attribute-mutation when
`dry_run=True`. The reported `IngestionStats` are therefore a genuine
preview - verified by a test asserting a dry-run and a real run against
the same input produce identical stats.

## 11. Reproducibility

`tests/fixtures/osm/sample_extract.osm` is a small, hand-authored,
synthetic OSM XML extract (not real-world data, no licensing concern) -
7 nodes, 6 ways - covering: a shared junction node forcing a way split, a
bidirectional road, a forward one-way road, a reverse (`oneway=-1`) road,
road names, optional `maxspeed`/`lanes`, an unsupported highway value, a
too-few-nodes malformed way, and an unresolvable node reference. All
automated tests run against this fixture; none depend on network access
or a real OSM download.

## 12. CLI / interface

`services/api/app/ingestion/cli.py`, run as
`uv run python -m app.ingestion.cli <path> [--dry-run] [--source osm]`
from `services/api` - a CLI, not an HTTP endpoint (doc 05 is not modified;
TASK-202 §14 explicitly prefers a CLI and doesn't require public API
exposure). Follows the same `get_session_factory()`/`dispose_engine()`
pattern `app/db/seed.py` established in TASK-201.

## 13. Placement decision (flagged for architect review)

Ingestion code lives at `services/api/app/ingestion/osm/`, inside the
existing `services/api` FastAPI service - **not** under the
`services/ingestion/` directory doc 10 reserves for a future microservice.
Doc 10 scopes `services/ingestion/` to "telemetry/static-data/incident
ingestion... doc 06", explicitly a Phase 3 (real-time) build; standing up
a whole new service/container for a CLI-only, Phase 2 concern would add
deployment complexity the task didn't ask for (§14: "Do not expose
ingestion as a public HTTP API unless the architecture explicitly
requires it"). Flagging this placement choice explicitly rather than
silently assuming it's correct - it can move to `services/ingestion/`
once that service actually exists.

## 14. Known limitations (complete list)

- `.osm` XML only, not `.osm.pbf` - avoids adding a new native dependency
  (osmium/pyosmium) for this initial implementation; stdlib
  `xml.etree.ElementTree.iterparse` is memory-bounded and sufficient for a
  bounded extract.
- Road grouping by bare `name` string can over-merge same-named, unrelated
  roads within one extract (§5).
- `oneway=reversible`/`alternating` treated as unrestricted, not modeled
  as time-dependent (§7).
- `access` tag is captured but not filtered/acted on - no access-aware
  logic exists yet (correctly deferred; nothing downstream needs it until
  routing work does).
- Geometry length is a flat-degrees-to-meters estimate
  (`geometry.py:_DEGREES_TO_METERS_AT_EQUATOR`), not a geodesic
  calculation - adequate for a cached display/estimate field, not for
  anything routing-precision-sensitive.
- One transaction per ingestion run (§9) - fine at this task's scale, would
  need chunking for a genuinely large dataset.
- No area/polygon disambiguation (a `highway=pedestrian` tagged as an area
  rather than a line isn't specially detected) - deferred as unnecessary
  complexity for the current scope.

---
*v1.0 — TASK-202.*
