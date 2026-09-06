# TASK-204 Design — Real-Time Vehicle Telemetry & Network State Engine

Companion to [PHASE2_DESIGN.md](PHASE2_DESIGN.md) (TASK-201),
[TASK202_DESIGN.md](TASK202_DESIGN.md) (TASK-202), and
[TASK203_DESIGN.md](TASK203_DESIGN.md) (TASK-203). Documents the decisions
made building AURA's telemetry ingestion pipeline and current-state
engine - the first *dynamic* layer over the static PostGIS network /
computational graph those three tasks established.

## 1. Telemetry event model

Minimum required fields (`app/schemas/telemetry.py:TelemetryIngestRequest`):
`vehicle_id`, `timestamp`, `latitude`, `longitude`, `speed_mps`, `source`.
Optional: `heading_deg` ("where available", per this task's brief),
`accuracy_m` (has an immediate consumer - segment-association confidence
- unlike `altitude`/`battery`/device metadata, which are deliberately
**not** added: no consumer exists yet, and "every field must have a
clear purpose" was explicit in this task's brief).

Deliberately narrower than doc 06 §6.1's original `VehicleTelemetry`
JSON shape - see §2 below for why `route_id`/`trip_id` and `occupancy`
were dropped.

## 2. Architecture reconciliation

Read: docs 01/03/04/05/06/10/12/13/14/15, TASK202_DESIGN.md,
TASK203_DESIGN.md, ARCHITECTURE_REVIEW.md, plus the actual
`Vehicle`/`VehicleAssignment`/`Route` models, `RedisManager`, the
exceptions/API-router conventions, and the full existing test suite.

**No blocking ambiguity** - every discrepancy found was already resolved
by this task's own brief, the same pattern TASK-202 used for its
migration-0003 correction:

- **`route_id`/`trip_id` on the wire contract (doc 06 §6.1).** doc 04's
  `trips` table was never built - TASK-201 deliberately built
  `vehicle_assignments` instead, kept independent of a specific journey
  instance (PHASE2_DESIGN.md §2.3). Embedding `route_id`/`trip_id` on
  every raw GPS ping would also conflate "where is the vehicle" with
  "what is it assigned to" - exactly what this task's §15 says not to do.
  **Resolution:** dropped from the wire contract; `VehicleAssignment` is
  resolved separately, on read (§8/§13 below).
- **`occupancy` (doc 06 §6.1).** A demand-prediction (FR-PRED-04) input
  with no consumer in this codebase yet. **Resolution:** dropped - "do
  not add fields merely because they might be useful someday."
- **`telemetry.matched_edge_id` (doc 04, "text ... OSM edge id").**
  Predates TASK-203's canonical graph, which keys every edge by
  `road_segments.id` (uuid), never a raw OSM way/edge id.
  **Resolution:** corrected to `road_segment_id uuid FK -> road_segments`;
  doc 04 updated in place (§14 below), same pattern as migration 0003.
- **Event identity (doc 06 §6.1a vs. this task's §3).** This task's brief
  asks for an explicit "event identifier / idempotency identifier" field;
  doc 06 already defines a deterministic idempotency key as the composite
  `(vehicle_id, ts, source)`, already reviewed at Phase 0.
  **Resolution:** the composite natural key **is** the event identity -
  no separate synthetic `event_id` column, avoiding a second identity
  mechanism that would need reconciling with the first (§3 below).
- **Unauthenticated write endpoint vs. doc 02.5/05.1 ("no unauthenticated
  write endpoints" / "JWT bearer auth on every endpoint").** No auth
  infrastructure of any kind exists anywhere in this codebase - no
  `users` table migration, no login endpoint, no JWT code - and every
  existing endpoint (TASK-201's `roads`/`stops`/`routes`/`vehicles`) is
  already unauthenticated. ARCHITECTURE_REVIEW.md §12 item 4 explicitly
  flagged "phone telemetry auth model" as a deferred human decision, not
  something to resolve unilaterally in code, and this task's own brief
  says not to build an elaborate auth system. **Resolution:** implemented
  unauthenticated, matching every existing endpoint (§15 below) - a
  documented, deliberate deviation, not an oversight.
- **doc 04 §4.4's FK-delete rule.** "All FK relationships are `ON DELETE
  RESTRICT` by default except `telemetry` and `predictions` ... should
  never block a parent delete." **Resolution:** `telemetry.vehicle_id`
  uses `ON DELETE CASCADE` (the only option compatible with a `NOT NULL`
  column that must never block a vehicle delete), not the RESTRICT
  default every other Phase-2 FK uses.

## 3. Idempotency

The event identity is the composite natural key `(vehicle_id, ts,
source)`, enforced by `uq_telemetry_vehicle_ts_source` and applied via
`INSERT ... ON CONFLICT (vehicle_id, ts, source) DO NOTHING RETURNING id`
(`app/telemetry/pipeline.py`) - the exact mechanism doc 06 §6.1a already
specifies. A pre-check (`_is_duplicate`) recognizes and reports a
duplicate before doing any of the more expensive work (segment
association); the `ON CONFLICT` clause is a second, race-safe guarantee
for a concurrent identical retry landing between the pre-check and the
insert. Both paths return `status: "duplicate"`, never an error - a
retried POST is a safe, idempotent no-op (FR-INGEST-06).

## 4. Ordering & stale-state policy

Two genuinely distinct concerns, deliberately kept separate
(`app/telemetry/freshness.py`):

- **Ordering** (`is_newer`): does *this* incoming, already-validated event
  advance the vehicle's current state? Compared against the state's
  timestamp *before* this event is inserted (a real bug caught during
  testing - see §19) - an out-of-order sample (the exact TASK-204 §4
  example: 14:00:11 arriving after 14:00:12) is still persisted to
  history but never regresses the cached current state.
- **Freshness** (`classify_freshness`): a read-time classification of how
  long it's been since the current state last advanced - `live` / `stale`
  / `offline`, not a property of any single telemetry event.

These are not the same as **validation's** timestamp-skew check (§6): a
grossly wrong timestamp (an hour old, or minutes in the future) is
*rejected*, never persisted at all; a merely out-of-order-but-recent
timestamp is *accepted* and persisted, just doesn't advance state.

## 5. Stale-state thresholds

Three tiers, both boundaries configurable (`app/core/config.py`), not
hardcoded:

| Setting | Default | Rationale |
|---|---|---|
| `telemetry_stale_threshold_s` | 15s | Matches doc 06 §6.1b's already-specified default exactly (three missed samples at the 1-per-5s cadence, doc 01 INGEST-01). |
| `telemetry_offline_threshold_s` | 300s (5 min) | New for this task - doc 06 only defined one threshold ("stale"). A round, clearly-labeled default for "very likely off/out of coverage," not empirically tuned - revisit once real fleet behavior is observed. |

`age_s <= stale_threshold_s` -> `live`; `stale_threshold_s < age_s <=
offline_threshold_s` -> `stale`; beyond that -> `offline`. A vehicle with
**no** telemetry ever is a distinct case - `get_vehicle_state` returns
`None`, not an `offline` state (§8).

## 6. Validation

`app/telemetry/validation.py:validate_fields` - policy checks that need
runtime config or "now," which don't belong in a Pydantic model:

- **Speed ceiling** (`telemetry_max_speed_mps`, default 40.0 m/s /
  ~144 km/h) - matches doc 06 §6.1's existing value exactly; a
  configurable sensor-error cutoff, not a physical law, so it's
  policy-layer, not a DB `CHECK` constraint (see §14).
- **Clock skew** (`telemetry_max_clock_skew_past_s`=30,
  `telemetry_max_clock_skew_future_s`=5) - matches doc 06 §6.1's `[-30s,
  +5s]` window exactly, relative to the server's receipt time.
- **Timezone-aware timestamp required** - a naive timestamp is
  deterministically rejected rather than silently assumed to be UTC.

Structural checks (coordinate range, non-negative speed/accuracy, heading
`[0, 360)`) are enforced by `TelemetryIngestRequest`'s Pydantic field
constraints instead - always true, never configurable, so they don't
belong in this module. **Known vehicle** is checked separately in the
pipeline (`_vehicle_exists`) since it requires a database query this pure
module deliberately doesn't perform.

## 7. Segment association

`app/telemetry/segment_association.py:find_nearest_segment` - the
nearest canonical `RoadSegment` within a configurable radius
(`telemetry_segment_search_radius_m`, default 50m), via `ST_DWithin`/
`ST_Distance` (geography-cast, reusing the exact pattern
`app/repositories/stops.py:find_stops_near` already established) plus
`ST_LineLocatePoint` for a 0-1 progress fraction along the segment.

**This is explicitly not map matching.** It answers "which RoadSegment is
geometrically closest," not "which path is the vehicle actually
following given trajectory and topology" (FR-FUSE-02's fuller definition)
- no heading, no recent-history, no graph-connectivity reasoning is used.
No match within the radius is a normal, expected outcome (a GPS fix off
any mapped road, or - as in several of this task's own tests - a network
too sparse to have a segment nearby), not an error: `road_segment_id`
stays `NULL` on the persisted row and the event is still accepted.

## 8. Current vehicle state

`app/telemetry/state.py:CurrentVehicleState` / `get_vehicle_state`.
Redis-first (`aura:vehicle_state:{vehicle_id}`, JSON, TTL-bounded - §10),
falling back to Postgres's `telemetry` table (latest row by `ts`) on a
cache miss or Redis outage (§11/§17). `get_vehicle_state` returns `None`
only when the vehicle has **never** reported telemetry at all - distinct
from `offline` (§5), which still returns a state, just a stale one.
`active_assignment` (route/calendar) is resolved on every read via
`VehicleAssignment` (§13), never stored on the cached/persisted state
itself. Current state is deliberately *not* the full telemetry history
(§9) - it's the latest valid operational snapshot only.

## 9. Historical persistence

`telemetry` (migration `0004`) is the durable, append-only history -
every valid, non-duplicate sample, regardless of arrival order (§4).
Bigserial `id` + a single `created_at` (no `updated_at`) rather than the
usual `UUIDPrimaryKeyMixin`/`TimestampMixin` pair, matching
`app/models/mixins.py`'s own note that this exact append-only,
high-volume table needs different treatment. Never truncated or rewritten
by this task's code (§16).

## 10. Redis's role

Cache only, never the source of truth: `aura:vehicle_state:{vehicle_id}`
holds the latest `CurrentVehicleState` as JSON, with a TTL
(`telemetry_state_cache_ttl_s`, default 1800s = 6x the offline threshold)
so a vehicle that stops transmitting forever doesn't grow the keyspace
unboundedly (§21 performance). No Redis Streams, no consumer groups -
`app/cache/redis.py`'s own existing comment says explicitly not to build
those yet ("the intended home for the Streams/pub-sub helpers ... for
later phases"); this task honors that.

## 11. API design

| Method | Path | Notes |
|---|---|---|
| POST | `/api/v1/telemetry` | Single-event ingestion, matching doc 05 §5.2's path exactly. `202` on both `accepted` and `duplicate` (both are successful idempotent outcomes); `422` (doc 05's structured error envelope) on rejected/unknown-vehicle. |
| GET | `/api/v1/fleet` | All vehicles with any recorded telemetry, current state. |
| GET | `/api/v1/fleet/{vehicle_id}` | Single vehicle's current state; `404` if it has never reported telemetry. |

`/fleet`/`/fleet/{vehicle_id}` were **not** invented as new paths -
doc 05 §5.3 already specifies exactly this shape ("current position,
speed, delay, status, anomaly flags") for real-time state, distinct from
TASK-201's static `/vehicles` registry. Following the documented
convention instead of this task's own "conceptually: `GET
/vehicles/{id}/state`" suggestion avoids a competing concept, per this
task's own "avoid unnecessary endpoint proliferation" instruction.
`/telemetry/batch` (doc 05) is **not** implemented - not required by this
task's brief, which only asks for the conceptual single-event path; can
be added later without a breaking change.

## 12. Real-time publication boundary

`app/telemetry/publisher.py:publish_state_update` - the one place the
pipeline calls after an event advances a vehicle's state. Today it's a
thin wrapper over the Redis cache write; this is the seam a future task
attaches Redis Streams or WebSocket fan-out to, without the ingestion
pipeline itself needing to change (§10 - Streams are explicitly not built
yet, per `app/cache/redis.py`'s own existing guidance).

## 13. Vehicle assignment integration

`app/repositories/telemetry.py:get_active_assignment` resolves a
vehicle's active `VehicleAssignment` (status=`active`, `valid_from <=
today <= valid_to or NULL`) on every state read - never stored on a
telemetry row, never a new competing "current route" concept. **Known
simplification:** does not check the assignment's `ServiceCalendar`
day-of-week bits (e.g. a weekday-only assignment still "resolves" on a
weekend) - a documented scope decision, not a correctness claim about
which specific day the assignment actually runs (§17).

## 14. Database changes

One migration (`0004_vehicle_telemetry.py`): a single new `telemetry`
table (columns/constraints/indexes in §1/§3/§7/§9 above), no changes to
any existing table. `road_segments`/`intersections`/the TASK-203 graph
are read-only from this table's perspective - nothing here ever writes
back into the canonical network. doc 04 is updated in place to replace
its original `telemetry` shape with what actually shipped (§2).

Numeric range constraints that are always true regardless of policy
(`speed_mps >= 0`, `heading_deg` in `[0, 360)`, `segment_progress` in
`[0, 1]`, `accuracy_m >= 0`) are enforced as DB `CHECK` constraints -
matching the existing `route_stops.sequence >= 0` precedent. The
*configurable* speed ceiling (§6) deliberately is **not** a DB
constraint, since it's an application policy value that can change
without a schema migration.

## 15. Security

Unauthenticated, matching every existing endpoint in this codebase (§2's
reconciliation finding) - a deliberate, documented deviation from doc
02.5/05.1's "no unauthenticated write endpoints," not an oversight. At
this stage: FastAPI/Pydantic's own request-body size limits and strict
schema validation reject malformed/oversized payloads before any
processing; coordinate/speed/heading range checks (§6) reject
out-of-bounds input; vehicle-existence checks (§2) reject spoofed
`vehicle_id`s. No new authentication system was built, per this task's
explicit instruction. Real auth (JWT or the lighter per-device token
scheme ARCHITECTURE_REVIEW.md §12 item 4 raised as an alternative) is
future work.

## 16. Testing

- **Unit** (28 tests, no database): `validate_fields` (speed ceiling,
  clock skew, timezone-awareness, plus Pydantic field-constraint
  coverage for coordinates/speed/heading/accuracy/source/required
  fields), `is_newer`/`classify_freshness` (pure ordering/freshness
  logic, including the exact §4 out-of-order example), and the Redis
  JSON (de)serialization round-trip.
- **Integration** (21 tests, real PostGIS + Redis): valid ingest,
  duplicate recognition, the out-of-order scenario end-to-end, clock-skew
  rejection, unknown-vehicle rejection, segment association (match and
  no-match), `get_vehicle_state`'s Postgres fallback on a cache miss,
  freshness classification at read time, active-assignment resolution
  (present and absent), and the segment-observation network-state
  aggregation (§23 concept - count/mean-speed, and window exclusion).
- **API** (9 tests): valid/duplicate/unknown-vehicle/malformed-coordinate/
  missing-field/stale-clock-skew requests, the doc 05 error envelope, and
  both `/fleet` endpoints' response contracts.
- **Regression**: all 135 pre-existing TASK-201/202/203 tests still pass
  unmodified in behavior - one, `test_database_is_at_expected_alembic_head`,
  was updated to expect the new migration head (`0004`), the same kind of
  expected maintenance TASK-202 needed when it added migration `0003`.
- **Deterministic fixtures** (`tests/fixtures/telemetry.py`): a factory
  building `TelemetryIngestRequest` instances with caller-controlled
  timestamps/coordinates/speed - no real phones, GPS services, or network
  access, satisfying this task's §21 without a separate standalone
  producer script (the fixture module *is* the "synthetic telemetry
  producer" this task's testing section asks for).

## 17. Known limitations

- Segment association is nearest-neighbour only, not true map matching
  (§7) - explicitly named as such, not oversold.
- `ST_LineLocatePoint`'s progress fraction is planar/degrees-based, not
  geodesic - the same class of approximation TASK-202 already documented
  for its length estimate, adequate at this scale.
- `get_active_assignment` ignores `ServiceCalendar` day-of-week bits
  (§13).
- No service-area bounding-box validation (doc 06 mentions one, but no
  specific demo area/bounds has been chosen anywhere in this project yet)
  - only basic lat/lon range validation exists; add the box once a
  concrete service area is picked.
- Ingestion runs synchronously inside the HTTP request - no async queue
  or background worker. Acceptable at this task's stated foundational
  scope; a Redis-Streams-based async pipeline is future work once
  multiple real consumers exist (doc 06's fusion-worker/prediction/WS-
  fan-out topology), not before.
- No retention/deletion job - doc 15.6 suggests a 30-day raw-telemetry
  window as an eventual ops policy, but this task deliberately does not
  implement automatic deletion ("preserving data is preferable").
- `GET /fleet` iterates vehicles one `get_vehicle_state` call at a time
  rather than a single bulk query - acceptable at this task's declared
  scale (doc 02.2: <=100 concurrent vehicles); revisit if that changes.

## 18. Future evolution

- Redis Streams (`stream:telemetry:raw`/`stream:telemetry:fused`, doc 06
  §6.2) attach at the `publish_state_update` seam (§12) without changing
  the ingestion pipeline itself.
- WebSocket fan-out (doc 05 §5.9 `/ws/live`) is a subscriber to that same
  seam, not a change to how telemetry is ingested or stored.
- True map matching (trajectory + heading + graph connectivity, using
  TASK-203's graph rather than a single nearest-neighbour query) replaces
  `find_nearest_segment` without changing the `telemetry` table shape -
  `road_segment_id`/`segment_distance_m`/`segment_progress` already are
  the columns a real map-matcher would populate more accurately.
- The `get_segment_observation` aggregation (§ "network state," doc 04
  §23) is the natural feature input for a future traffic-prediction task
  - deliberately not built into anything predictive here.
- A real auth mechanism (§15) once the project-wide decision
  ARCHITECTURE_REVIEW.md §12 item 4 flagged is actually made.

---
*v1.0 — TASK-204.*
