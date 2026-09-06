# 4. Data Model (ER)

PostgreSQL + PostGIS. Geometry columns use `GEOMETRY(Point, 4326)` /
`GEOMETRY(LineString, 4326)` (WGS84) unless noted. This is the v1 schema —
expect additive migrations as phases land; do not treat column lists as final.

## 4.1 ER diagram

```mermaid
erDiagram
    ROUTES ||--o{ TRIPS : has
    ROUTES ||--o{ ROUTE_STOPS : has
    STOPS ||--o{ ROUTE_STOPS : has
    VEHICLES ||--o{ TRIPS : assigned_to
    TRIPS ||--o{ TELEMETRY : produces
    TRIPS ||--o{ PREDICTIONS : has
    ROUTES ||--o{ TRAFFIC_OBSERVATIONS : has
    STOPS ||--o{ DEMAND_OBSERVATIONS : has
    INCIDENTS ||--o{ RECOMMENDATIONS : triggers
    RECOMMENDATIONS ||--o{ SIMULATION_RUNS : evaluated_by
    SIMULATION_RUNS ||--o{ SIMULATION_RESULTS : produces
    RECOMMENDATIONS ||--o{ AUDIT_LOGS : recorded_in
    MODEL_VERSIONS ||--o{ PREDICTIONS : produced_by
    MODEL_VERSIONS ||--o{ RECOMMENDATIONS : produced_by
    USERS ||--o{ AUDIT_LOGS : acts_in
    ROADS ||--o{ ROAD_SEGMENTS : aggregates
    INTERSECTIONS ||--o{ ROAD_SEGMENTS : starts
    INTERSECTIONS ||--o{ ROAD_SEGMENTS : ends
    VEHICLES ||--o{ VEHICLE_ASSIGNMENTS : assigned_via
    ROUTES ||--o{ VEHICLE_ASSIGNMENTS : served_by
    SERVICE_CALENDARS ||--o{ VEHICLE_ASSIGNMENTS : scopes
```

Phase 2 (TASK-201) added `intersections`/`roads`/`road_segments` (the
physical road network — PostGIS is the system of record, not an in-memory
graph — see [PHASE2_DESIGN.md](PHASE2_DESIGN.md)) and
`service_calendars`/`vehicle_assignments` (static fleet planning,
independent of `trips`).

## 4.2 Tables

**Phase 2 addition (see [PHASE2_DESIGN.md](PHASE2_DESIGN.md)):** the road
network (`intersections`, `roads`, `road_segments`) is now a first-class,
persisted part of this schema — PostGIS is the system of record for road
topology; an in-memory NetworkX/OSMnx graph used by routing work is a
*derived* view rebuilt from these tables, never the source of truth. This
was unspecified (not contradicted) by the original v1.0 schema below;
`stops`/`routes`/`vehicles`/`route_stops` below are also extended with
`name`/`source`/`source_id`/audit-timestamp columns per that document —
the column lists below are updated in place to reflect what actually
shipped, with the original v1.0 intent preserved.

### `users`
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| email | text unique | |
| role | text | `controller`, `admin`, `viewer` |
| password_hash | text | |
| created_at | timestamptz | |

### `intersections` *(Phase 2)*
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| location | geometry(Point,4326) | |
| source | text | `osm` \| `manual` |
| osm_node_id | bigint, unique when present | idempotency key for OSM ingestion |
| created_at, updated_at | timestamptz | |

### `roads` *(Phase 2)*
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| name | text nullable | human-meaningful name, e.g. "MG Road"; a Road aggregates 1+ RoadSegments |
| road_class | text nullable | |
| source | text | `osm` \| `manual` |
| created_at, updated_at | timestamptz | |

### `road_segments` *(Phase 2)*
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| road_id | uuid FK → roads, nullable | a segment need not belong to a named Road |
| start_intersection_id | uuid FK → intersections | |
| end_intersection_id | uuid FK → intersections | |
| geometry | geometry(LineString,4326) | the routable unit — one edge between two intersections |
| length_m | double precision nullable | cached; computable via `ST_Length(geography(geometry))` |
| is_oneway | boolean | |
| road_class | text nullable | |
| source | text | `osm` \| `manual` |
| osm_way_id | bigint, unique when present | idempotency key for OSM ingestion |
| created_at, updated_at | timestamptz | |

### `vehicles`
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| external_code | text unique | e.g. "BUS_07" |
| capacity | int | |
| source | text | `real` \| `simulated` (CHECK constraint, Phase 2) |
| status | text | `active`, `spare`, `maintenance` (CHECK constraint, Phase 2) |
| created_at, updated_at | timestamptz | *(Phase 2)* |

### `vehicle_assignments` *(Phase 2 — static fleet planning, not a trip)*
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| vehicle_id | uuid FK → vehicles | |
| route_id | uuid FK → routes | |
| service_calendar_id | uuid FK → service_calendars | |
| valid_from | date | |
| valid_to | date nullable | open-ended if null |
| status | text | `active` \| `ended` |
| created_at, updated_at | timestamptz | |

Independent of `trips` below (see [PHASE2_DESIGN.md](PHASE2_DESIGN.md)
§2.3) — this is "which vehicle serves which route, for which calendar
period" at the fleet-planning level, not a specific journey instance.

### `service_calendars` *(Phase 2 — GTFS calendar.txt-equivalent)*
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| code | text unique | e.g. "WEEKDAY" |
| monday..sunday | boolean × 7 | |
| start_date, end_date | date | |
| created_at, updated_at | timestamptz | |

### `routes`
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| code | text unique | e.g. "Route 12" |
| name | text nullable | *(Phase 2)* |
| geometry | geometry(LineString,4326) nullable | *(Phase 2: relaxed to nullable — a route may exist before its path is computed)* |
| direction | text | |
| source | text | `osm` \| `gtfs` \| `manual` *(Phase 2)* |
| source_id | text nullable | idempotency key when source ≠ manual *(Phase 2)* |
| created_at, updated_at | timestamptz | *(Phase 2)* |

### `stops`
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| code | text unique | |
| name | text nullable | *(Phase 2)* |
| location | geometry(Point,4326) | |
| capacity_hint | int | for crowding threshold |
| source | text | `osm` \| `gtfs` \| `manual` *(Phase 2)* |
| source_id | text nullable | idempotency key when source ≠ manual *(Phase 2)* |
| created_at, updated_at | timestamptz | *(Phase 2)* |

### `route_stops`
| Column | Type | Notes |
|---|---|---|
| route_id | uuid FK → routes | |
| stop_id | uuid FK → stops | not unique — a loop route may revisit a stop at a different sequence position |
| sequence | int | order along route |
| scheduled_offset_s | int | seconds from trip start |
| created_at, updated_at | timestamptz | *(Phase 2)* |

PK: **(route_id, sequence)** — not `(route_id, stop_id, sequence)`. Sequence
alone determines position along a route; including `stop_id` in the key
would let two different stops share the same sequence number for the same
route, which is not a valid route. Index `stop_id` separately for
"which routes serve this stop" lookups.

### `trips`
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| route_id | uuid FK → routes | |
| vehicle_id | uuid FK → vehicles | |
| scheduled_start | timestamptz | |
| actual_start | timestamptz nullable | |
| status | text | `scheduled`, `active`, `completed`, `cancelled` |

### `telemetry`
| Column | Type | Notes |
|---|---|---|
| id | bigserial PK | |
| vehicle_id | uuid FK → vehicles | |
| trip_id | uuid FK → trips nullable | |
| ts | timestamptz | |
| location | geometry(Point,4326) | |
| speed_mps | real | |
| heading_deg | real | |
| occupancy | int nullable | |
| matched_edge_id | text nullable | OSM edge id after map-matching |
| source | text | `phone`, `sumo` |

Indexed on `(vehicle_id, ts)`; hypertable-style partitioning by day is a
reasonable future optimization, not required for v1 scale (doc 02.2).

**Idempotency:** unique constraint on `(vehicle_id, ts, source)`. A retried
POST from a flaky phone/SUMO connection carries the same `(vehicle_id,
timestamp, source)` and is written with `ON CONFLICT (vehicle_id, ts,
source) DO NOTHING` — safe to retry without creating duplicate rows that
would double-count in speed/headway aggregation. This is the mechanism
behind FR-INGEST-06's dedup requirement (see doc 06 §6.1a).

### `traffic_observations`
| Column | Type | Notes |
|---|---|---|
| id | bigserial PK | |
| edge_id | text | OSM edge id |
| ts | timestamptz | |
| avg_speed_mps | real | |
| sample_count | int | |
| source | text | `derived`, `sumo`, `historical_import` |

### `demand_observations`
| Column | Type | Notes |
|---|---|---|
| id | bigserial PK | |
| stop_id | uuid FK → stops | |
| ts | timestamptz | |
| boarding_count | int | |
| alighting_count | int | |
| source | text | |

### `incidents`
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| type | text | `accident`, `closure`, `breakdown`, `other` |
| location | geometry(Point,4326) | |
| affected_edge_ids | text[] | nullable |
| severity | text | `low`, `medium`, `high` |
| starts_at | timestamptz | |
| ends_at | timestamptz nullable | |
| reported_by | uuid FK → users nullable | |

### `model_versions`
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| model_name | text | e.g. `traffic_xgb`, `bunching_lstm`, `rl_dqn_v1` |
| version | text | **canonically the MLflow run id** (unambiguous, always unique); an optional separate `display_tag` field may hold a human semantic label like `v1.2` — don't use semantic tags as the canonical `version` value, they're not guaranteed unique across retraining |
| trained_at | timestamptz | |
| metrics | jsonb | MAE/RMSE/etc. at training time |
| artifact_uri | text | DVC/MLflow reference |

### `predictions`
| Column | Type | Notes |
|---|---|---|
| id | bigserial PK | |
| model_version_id | uuid FK → model_versions | |
| target_type | text | `traffic`, `eta`, `delay`, `demand`, `bunching` |
| target_ref_id | **text** | polymorphic: `trip_id`/`stop_id` (uuid, stored as text) for eta/delay/demand, OSM **edge_id** (not a uuid — see doc 07) for traffic. Documented per target_type; never typed `uuid` because edge_id isn't one. |
| horizon_s | int | prediction horizon in seconds |
| value | jsonb | schema depends on target_type (doc 07) |
| generated_at | timestamptz | |

Index: `(target_type, target_ref_id, generated_at DESC)` — the "latest
prediction for this target" lookup the API and decision engine both do on
every request.

### `recommendations`
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| trigger_type | text | `bunching`, `delay`, `incident`, `manual` |
| trigger_ref_id | uuid nullable | e.g. incident_id |
| candidate_actions | jsonb | list of {action, params} evaluated |
| selected_action | jsonb | the recommended one |
| explanation | jsonb | {cause, expected_impact, confidence} |
| model_version_id | uuid FK → model_versions nullable | RL agent version if RL-sourced |
| status | text | `pending`, `approved`, `rejected`, `expired` |
| created_at | timestamptz | |
| decided_at | timestamptz nullable | |
| decided_by | uuid FK → users nullable | |

### `simulation_runs`
| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| recommendation_id | uuid FK → recommendations nullable | null for standalone what-if runs |
| scenario_name | text | see doc 09 scenario library |
| action | jsonb | candidate action simulated, or null for baseline |
| seed | int | for reproducibility (FR-SIM-02) |
| started_at | timestamptz | |
| finished_at | timestamptz nullable | |
| status | text | `running`, `completed`, `failed` |

### `simulation_results`
| Column | Type | Notes |
|---|---|---|
| id | bigserial PK | |
| simulation_run_id | uuid FK → simulation_runs | |
| avg_wait_s | real | |
| avg_delay_s | real | |
| bunching_events | int | |
| fleet_utilization_pct | real | |
| fuel_proxy | real | SUMO emission model output |
| co2_proxy | real | |

### `audit_logs`
| Column | Type | Notes |
|---|---|---|
| id | bigserial PK | |
| recommendation_id | uuid FK → recommendations nullable | |
| user_id | uuid FK → users nullable | null for system-generated entries |
| action | text | `viewed`, `approved`, `rejected`, `overridden` |
| reason | text nullable | |
| ts | timestamptz | |

## 4.3 Indexes

Not exhaustive, but every one of these is load-bearing for a specific FR/NFR
— don't defer them as "optimize later":

| Table | Index | Why |
|---|---|---|
| `intersections` | GIST on `location`; unique on `osm_node_id` | topology lookups; idempotent OSM ingestion |
| `road_segments` | GIST on `geometry`; btree on `road_id`, `start_intersection_id`, `end_intersection_id`; unique on `osm_way_id` | routing traversal; idempotent OSM ingestion |
| `vehicle_assignments` | btree on `vehicle_id`, `route_id`, `service_calendar_id` | fleet-planning lookups |
| `routes` | GIST on `geometry` | proximity/overlap queries (FR-ROUTE-01) |
| `stops` | GIST on `location` | nearest-stop lookups, map-matching support |
| `incidents` | GIST on `location`; btree on `(starts_at, ends_at)` | "active incidents" queries (FR-INGEST-05), incident-impact detection (FR-EVENT-02) |
| `telemetry` | GIST on `location`; btree on `(vehicle_id, ts)` (existing); unique on `(vehicle_id, ts, source)` | map-matching (FR-FUSE-02), idempotency (above) |
| `traffic_observations` | btree on `(edge_id, ts)` | traffic model feature lookup (doc 07 §7.1) |
| `demand_observations` | btree on `(stop_id, ts)` | demand model feature lookup (doc 07 §7.4) |
| `predictions` | btree on `(target_type, target_ref_id, generated_at DESC)` | "latest prediction for X" (see above) |
| `recommendations` | btree on `(status, created_at)` | `/recommendations?status=pending` (doc 05 §5.6) |
| `simulation_runs` | btree on `(recommendation_id)` | fetching all candidate runs for a recommendation |
| `audit_logs` | btree on `(recommendation_id)`, `(user_id, ts)` | audit trail queries |

## 4.4 Notes

- `predictions.value` and `recommendations.explanation` are `jsonb` because
  their shape varies by target/action type — the authoritative shape for each
  is defined in doc 07 (ML contracts) and doc 08 (RL contracts), not here.
  Do not add a new top-level table per model type; extend the jsonb schema
  and document it.
- All FK relationships are `ON DELETE RESTRICT` by default except `telemetry`
  and `predictions`, which are append-only history and should never block a
  parent delete in practice (vehicles/trips are not expected to be hard-deleted).

---
*v1.1 — Phase 0 baseline, Phase 2 (TASK-201) additions applied in place.
See [PHASE2_DESIGN.md](PHASE2_DESIGN.md) for the reasoning behind every
Phase 2 change.*
