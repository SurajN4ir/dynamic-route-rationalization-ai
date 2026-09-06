# TASK-203 Design — Canonical Road Graph Construction

Companion to [PHASE2_DESIGN.md](PHASE2_DESIGN.md) (TASK-201) and
[TASK202_DESIGN.md](TASK202_DESIGN.md) (TASK-202). Documents the decisions
made building AURA's in-memory computational road graph, derived from the
canonical PostGIS transportation network those two tasks established.

## 1. Architecture reconciliation

Read: PHASE2_DESIGN.md, TASK202_DESIGN.md, docs 01/03/04/05/10/12/13/14/15,
`app/models/road_network.py`, migration `0002`/`0003`, the OSM ingestion
package, and `docs/architecture/ARCHITECTURE_REVIEW.md`.

**No material ambiguity found.** TASK-202's normalization already fully
resolves directed-edge semantics into two columns on `RoadSegment`:
`is_oneway` (bool) and `start_intersection_id`/`end_intersection_id` (UUIDs,
already ordered so that `start -> end` is the allowed travel direction -
TASK202_DESIGN.md §7 describes how ingestion reverses a `oneway=-1` way's
node order *before* this pair is ever written). The graph builder's rule is
therefore exactly: `is_oneway=False` -> emit both directed edges;
`is_oneway=True` -> emit only the forward edge. No raw OSM tag is
reinterpreted anywhere in `app/graph/` - see §7 for how this was verified.

One correction was needed to a *different* document, not the schema: doc
12's Phase 2 section still described TASK-203 as "in-memory
NetworkX/OSMnx graph construction ... and basic A*/Dijkstra routing over
that graph." That combined scope was split before this task's requirements
were written - TASK-203 as actually specified and built is graph
construction only; routing algorithms are explicitly out of scope (§9,
§14 below) and deferred to a future task. Doc 12 is corrected to match
(see the [12-development-phases.md](12-development-phases.md) diff
alongside this doc).

## 2. Graph model

`G = (V, E)`, directed:

| Canonical PostGIS | Graph element |
|---|---|
| `Intersection` row | one graph node, keyed by `Intersection.id` |
| `RoadSegment` row | one or two directed graph edges (§5), keyed by `RoadSegment.id` |

PostGIS remains authoritative (PHASE2_DESIGN.md's "system of record"
principle) - the graph is rebuilt from it on demand (§10) and is never
itself written back to. `app/graph/builder.py` only ever issues `SELECT`
statements against `intersections`/`road_segments`.

## 3. Node identity

A node's identity **is** `Intersection.id` (the canonical UUID primary
key) - not an array index, not object identity, not a synthesized counter.
This is what makes every edge's `(u, v)` pair directly meaningful as
canonical foreign keys, and what makes `test_case_g` (rebuild determinism)
a meaningful comparison rather than a coincidence of iteration order.

## 4. Edge identity and traceability

Each directed edge's `NetworkX` **key** is the `RoadSegment.id` it was
derived from (`app/graph/types.py:EdgeAttrs`). A `MultiDiGraph` requires
either an auto-incrementing integer key or an explicit one; using the
canonical UUID directly means `graph.has_edge(u, v, key=road_segment_id)`
*is* the traceability link back to PostGIS - no side table, no naming
convention to keep in sync. Every edge additionally carries
`road_segment_id` as a plain attribute (redundant with the key, kept for
callers that iterate `edges(data=True)` without also requesting `keys=True`).

Retained edge attributes: `road_segment_id`, `road_id`, `source`,
`osm_way_id`, `way_seq`, `is_oneway`, `reversed`, `road_class`, `length_m`,
`weight` (alias of `length_m`), `maxspeed_kph`, `lanes`, `access`. This is
every `RoadSegment` column with a plausible current-or-planned consumer
(§6 covers `weight` specifically); geometry is deliberately excluded (§8).

## 5. Multi-edge decision: `MultiDiGraph`

`road_segments` has no uniqueness constraint on
`(start_intersection_id, end_intersection_id)` - two distinct segments
(e.g. divided carriageways, or two unrelated short connector roads that
happen to share endpoints) can legitimately connect the same intersection
pair. A plain `DiGraph` would silently collapse them into one edge,
destroying the ability to trace back to two different canonical rows.
`nx.MultiDiGraph` is used specifically because preserving distinct
`RoadSegment` identity matters more than forcing a simple graph (verified
by `test_case_e_multiple_segments_between_same_pair_stay_distinct`).

A bidirectional segment (`is_oneway=False`) produces **two** `MultiDiGraph`
edges - `(start, end, key=segment_id)` and `(end, start, key=segment_id)`
- sharing the same key because they trace back to the same one canonical
row; the `reversed` attribute (`False`/`True`) distinguishes them.

## 6. Self-loop decision: permitted

Nothing in the schema (migration `0002`/`0003`) forbids
`start_intersection_id == end_intersection_id`, and TASK-202's
topology-splitting logic could plausibly produce one from real loop-road
OSM data. The builder does not special-case or reject self-loops: a
one-way self-loop produces exactly one edge `(node, node, key=segment_id)`;
`is_oneway=False` is meaningless for a self-loop's own direction (there is
only one node to loop through) so no synthesized second edge is ever added
regardless of the flag - `builder.py`'s bidirectional branch is gated on
`start_id != end_id` specifically to avoid trying to add a second,
identical `(node, node, key=segment_id)` edge.

Validation (§11) needed a matching fix: a self-loop's "does the reverse
edge exist" query is the exact same `(u, v, key)` triple as the forward
check, so without an explicit early-exit a one-way self-loop would
incorrectly be flagged as `unexpected_reverse_edge` (there is no reverse
to find - the forward check already covers everything). `validation.py`
skips the reverse-direction checks entirely for `start_id == end_id`.

## 7. Directionality: no OSM reinterpretation

`app/graph/builder.py` reads only `RoadSegment.is_oneway` and the two
intersection-id columns - it never touches an OSM tag, never imports
anything from `app/ingestion/`, and never re-derives direction from
geometry or node order. This was a hard requirement (§2/§7 of this task's
brief) verified by `test_case_c_graph_follows_canonical_start_end_not_raw_osm_orientation`,
which constructs a segment with `start`/`end` already swapped (as
TASK-202's ingestion would produce for a `oneway=-1` way) and confirms the
graph edge follows the canonical columns, not any notion of "original" OSM
orientation.

## 8. Geometry strategy: reference-only

Edges carry `road_segment_id` (the traceability key, §4) but not the
segment's `LineString` geometry itself. Copying geometry into the graph
would create a second, driftable authoritative-looking geometry store,
which PHASE2_DESIGN.md's "PostGIS is the system of record" principle and
this task's own §5 explicitly steer away from. A consumer that needs the
actual geometry queries `road_segments.geometry` by `road_segment_id`.

Node coordinates (`x`=longitude, `y`=latitude) **are** copied, as plain
floats via `ST_X`/`ST_Y` SQL functions - not by parsing the `Point`
geometry in Python. This is the standard NetworkX/OSMnx node-coordinate
convention (any graph algorithm needs coordinates without a DB round trip)
and is lightweight, clearly-derived convenience data, not a second
geometry store - the canonical point geometry stays in
`intersections.location`.

## 9. Static edge-weight strategy

`length_m` (already computed and cached by TASK-202's ingestion, per
TASK202_DESIGN.md §2) is copied onto each edge and aliased as `weight` -
the NetworkX-conventional attribute name for algorithms that accept a
`weight=` parameter. No geometry re-parsing, no live/dynamic weighting
(free-flow speed, observed travel time, congestion) is introduced -
that's explicitly future-phase work this task must not anticipate beyond
leaving the attribute name conventional for it to attach to later.

## 10. NetworkX vs. OSMnx

**NetworkX only.** OSMnx's core value-add - parsing raw OSM data and
building a routable graph from it - is redundant here: TASK-202 already
normalized OSM into AURA's own canonical schema, and `app/graph/` never
touches OSM data at all (§7). Pulling in OSMnx merely because the project's
ultimate data source is OpenStreetMap would add a materially heavier
dependency footprint (geopandas, shapely's OSMnx-specific usage patterns,
requests, rtree, and their transitive dependencies) to gain nothing this
task needs. `networkx>=3.3,<4` was added to `pyproject.toml`
(`uv sync --extra dev` resolved it to `networkx==3.6.1` with **zero** new
transitive dependencies - it is pure Python with no required third-party
dependencies of its own).

## 11. Validation rules

`app/graph/validation.py:validate_graph()` never repairs data, only
reports (`ValidationReport.is_valid` / `.errors` / `.warnings`). It is
checked against an **independently queried** set of known intersection
ids (`app/graph/builder.py:load_known_intersection_ids()`, a fresh
`SELECT Intersection.id`) rather than the graph's own node set - checking
a graph against itself can never detect a real discrepancy.

| Code | Meaning |
|---|---|
| `orphan_graph_node` | a graph node has no matching `Intersection` row |
| `missing_graph_node` | an `Intersection` row has no corresponding graph node |
| `segment_references_unknown_start` / `_end` | a `RoadSegment`'s intersection id isn't in the known set |
| `missing_forward_edge` | a canonical segment produced no graph edge at all |
| `unexpected_reverse_edge` | a one-way segment has a reverse edge present |
| `missing_reverse_edge` | a bidirectional segment is missing its reverse edge |

All are reported as `error` severity (no `warning`-level check was needed
for anything TASK-203 checks - every condition above indicates a genuine
builder or data defect, not a benign edge case).

## 12. Graph statistics

`app/graph/stats.py:compute_stats()` - `node_count`, `edge_count`
(canonical `RoadSegment` rows, not directed edges), `directed_edge_count`
(actual graph edges - up to 2x `edge_count`), `self_loop_count`,
`parallel_edge_group_count` (distinct `(u, v)` pairs with 2+ edges, not
counted per-edge), `isolated_node_count` (zero-degree nodes),
`weakly_connected_component_count` (*weakly* connected - a directed graph
with one-way streets can easily be strongly disconnected while still
representing one real, traversable-in-some-direction road network), and
`total_length_m` (summed once per canonical segment - only non-`reversed`
edges are counted, so a bidirectional segment's length isn't doubled). No
performance/timing metrics are fabricated; the CLI logs an actual measured
`duration_s` separately, which is not part of `GraphStats` itself.

## 13. Lifecycle and rebuild strategy

The graph is built on demand, in-process, from a plain function call
(`build_road_graph(session)`) - no caching layer, no persistence, no
background job, no Redis-backed graph state, no separate graph service.
Every call performs a full rebuild from current canonical data; no
incremental-update path exists or is needed at this scale. This is the
simplest architecture that satisfies the task (§16/§17 of the brief
explicitly steer away from introducing infrastructure beyond what's
required), and matches TASK-202's CLI-first, no-new-service precedent
(TASK202_DESIGN.md §13).

## 14. CLI / interface boundary

`services/api/app/graph/cli.py`, run as
`uv run python -m app.graph.cli build` (prints `GraphStats`) or
`uv run python -m app.graph.cli validate` (builds, then also runs
`validate_graph()` and exits non-zero on any error) - a CLI, not an HTTP
endpoint, consistent with TASK-202's precedent and this task's explicit
"do not create an HTTP endpoint unless architecture requires it." Uses the
same `get_session_factory()`/single-`asyncio.run()`/`dispose_engine()`
pattern established by `app/ingestion/cli.py` (TASK202_DESIGN.md §12) -
`_run()` and `dispose_engine()` share one event loop, avoiding the
cross-loop pooled-connection bug TASK-202 found and fixed.

## 15. Serialization

`app/graph/serialization.py:graph_to_dict()` exists solely for
tests/debugging - deterministic, sorted-by-string-key plain-dict output,
never written to disk as a generated artifact and never used as a cache.
It exists because comparing two `nx.MultiDiGraph` objects for "same
topology and attributes" directly is awkward (dict ordering, object
identity); sorting node/edge keys makes two builds of the same canonical
data byte-for-byte comparable, which is exactly what
`test_case_g_rebuild_from_unchanged_data_is_identical` needs.

## 16. Performance approach

Two bulk queries total - one `SELECT` for all intersections (with
`ST_X`/`ST_Y` computed in SQL, not Python), one for all road segments -
both explicitly `ORDER BY` primary key for determinism (§17 below), then
pure in-memory graph construction. Not one query per node or edge, no
per-row geometry parsing (see §8: only two floats per node come from
PostGIS, no `Point`/`LineString` object construction happens in this
module at all).

## 17. Determinism

Both queries are explicitly ordered by primary key (`Intersection.id`,
`RoadSegment.id`) rather than relying on whatever order Postgres happens
to return - the same database state therefore always produces nodes and
edges inserted in the same order, and Python dicts (and NetworkX's
internal adjacency structures) preserve insertion order. Verified directly
by `test_case_g_rebuild_from_unchanged_data_is_identical`, which builds
twice from unchanged data and asserts `graph_to_dict()` output is
identical both times.

## 18. Database schema changes

**None.** The graph is derived entirely from the existing TASK-202 schema
(`intersections`, `road_segments`) - no new table, no new column, no new
migration. `app/graph/` performs read-only `SELECT` statements exclusively.

## 19. Known limitations

- No dynamic/weighted routing attributes (free-flow speed, observed
  travel time, congestion adjustment) - deliberately deferred; `weight`
  currently aliases static `length_m` only, ready for a future task to
  attach a different weighting scheme without a graph-model change.
- No caching/persistence of the built graph - every call is a full
  rebuild. Acceptable at this task's scale (bounded PostGIS tables); a
  future task could add caching if profiling shows it's needed.
- Road grouping / geometry-precision limitations already documented in
  TASK202_DESIGN.md §5/§14 propagate unchanged into the graph, since the
  graph is a direct derivation of that same canonical data.
- No routing algorithm (shortest-path, A*, Dijkstra, or otherwise) is
  implemented here - deliberately out of scope (§1); a future task
  consumes this graph to add one.

---
*v1.0 — TASK-203.*
