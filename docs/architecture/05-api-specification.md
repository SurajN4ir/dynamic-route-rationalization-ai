# 5. API Specification

Gateway: `services/api`, FastAPI, REST + one WebSocket endpoint. All endpoints
under `/api/v1`. JWT bearer auth on every endpoint except `/auth/login` and
`/healthz`. Response envelope on error:

```json
{ "error": { "code": "string", "message": "string", "details": {} } }
```

## 5.1 Auth

| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/auth/login` | `{email, password}` | `{access_token, role}` |
| POST | `/auth/refresh` | `{refresh_token}` | `{access_token}` |

## 5.2 Ingestion

**TASK-204 implements `POST /telemetry`** — see
[TASK204_DESIGN.md](TASK204_DESIGN.md) §11. Unauthenticated (§15 of that
doc — no auth infrastructure exists anywhere in this codebase yet; a
deliberate, documented deviation from this doc's own §5.1 blanket JWT
rule, not an oversight). `VehicleTelemetry`'s actual implemented shape
(doc 06 §6.1) drops `route_id`/`trip_id`/`occupancy` from the schema
below — see TASK204_DESIGN.md §2. `/telemetry/batch` and `/incidents` are
**not yet implemented** (still open Phase 3 work).

| Method | Path | Body | Response | Notes |
|---|---|---|---|---|
| POST | `/telemetry` | `VehicleTelemetry` (doc 06) | `202 {status:"accepted"\|"duplicate", ...}` | Used by phone client + SUMO bridge; `duplicate` is a successful idempotent no-op, not an error |
| POST | `/telemetry/batch` | `VehicleTelemetry[]` | `202 {accepted, rejected[]}` | Not yet implemented (TASK-204) |
| POST | `/incidents` | `{type, lat, lon, severity, starts_at, ends_at?}` | `201 {incident_id}` | requires `controller`/`admin` role; not yet implemented |
| GET | `/incidents?active=true` | — | `Incident[]` | Not yet implemented |

## 5.3 Fleet / network state

**TASK-204 implements `/fleet` and `/fleet/{vehicle_id}`** exactly as
specified below — see TASK204_DESIGN.md §8/§11. `routes`/`trips` rows are
unrelated to TASK-204 and remain not yet implemented for their real-time
aspects (`/routes`/`/routes/{route_id}`/`/routes/{route_id}/stops` exist
as TASK-201's *static* reference data, §5.3a below — `/trips/{trip_id}`
is not implemented, since `trips` itself was never built; see
TASK204_DESIGN.md §2).

| Method | Path | Response | Notes |
|---|---|---|---|
| GET | `/fleet` | `VehicleState[]` | current position, speed, delay, status, anomaly flags |
| GET | `/fleet/{vehicle_id}` | `VehicleState` | |
| GET | `/routes` | `Route[]` | |
| GET | `/routes/{route_id}` | `Route` | |
| GET | `/routes/{route_id}/stops` | `Stop[]` | ordered |
| GET | `/trips/{trip_id}` | `Trip` incl. current ETA per remaining stop | Not yet implemented — no `trips` table exists |

## 5.3a Transportation network (static reference data)

Phase 2 (TASK-201) foundation — roads, stops, routes, and the vehicle
registry as persisted, PostGIS-backed reference data. Distinct from
§5.3's `/fleet`/`/trips` above (real-time state, Phase 3): these answer
"what exists," not "where is it right now." Numbered `5.3a` rather than
renumbering subsequent sections, following the same convention as doc 06
§6.1a/§6.1b — §5.4 onward keep their existing numbers, since doc 04, doc
09, and ARCHITECTURE_REVIEW.md already cite them by number (§5.6, §5.9).
See [PHASE2_DESIGN.md](PHASE2_DESIGN.md) for the schema decisions behind
this surface.

| Method | Path | Response | Notes |
|---|---|---|---|
| GET | `/roads` | `Road[]` | |
| GET | `/roads/{road_id}` | `Road` incl. its `RoadSegment[]` | |
| GET | `/road-segments/{segment_id}` | `RoadSegment` | |
| GET | `/stops` | `Stop[]` | paginated (`limit`, `offset`) |
| GET | `/stops/nearby?lat=&lon=&radius_m=` | `Stop[]` | proximity query (PostGIS `ST_DWithin`/`ST_Distance`), nearest first |
| GET | `/stops/{stop_id}` | `Stop` | |
| GET | `/vehicles` | `Vehicle[]` | paginated (`limit`, `offset`); static registry — not §5.3's `/fleet` (real-time state) |
| GET | `/vehicles/{vehicle_id}` | `Vehicle` | |

`Road`/`RoadSegment`/`Stop` geometry fields are GeoJSON (`Point` or
`LineString`, SRID 4326 — see doc 04 §4.2). No write endpoints exist for
any of these yet — the tables are populated via ingestion (a later task),
not through this API.

## 5.4 Predictions

| Method | Path | Response | Notes |
|---|---|---|---|
| GET | `/predictions/traffic?edge_id=&horizon=300` | `TrafficPrediction` | horizon in seconds; one of 300/900/1800/3600 |
| GET | `/predictions/eta/{trip_id}` | `EtaPrediction[]` | per remaining stop |
| GET | `/predictions/delay/{trip_id}` | `DelayPrediction` | |
| GET | `/predictions/demand/{stop_id}?horizon=900` | `DemandPrediction` | |
| GET | `/predictions/bunching?route_id=` | `BunchingPrediction[]` | pairs currently at risk |

Response shapes match doc 07 exactly (the API does not reshape model output).

## 5.5 Alerts

| Method | Path | Response |
|---|---|---|
| GET | `/alerts?active=true` | `Alert[]` |
| POST | `/alerts/{id}/ack` | `{status:"acked"}` |

## 5.6 Recommendations

| Method | Path | Body | Response | Notes |
|---|---|---|---|---|
| GET | `/recommendations?status=pending` | — | `Recommendation[]` | |
| GET | `/recommendations/{id}` | — | `Recommendation` (full, incl. candidate_actions + simulation summary) | |
| POST | `/recommendations/{id}/simulate` | `{}` | `202 {simulation_run_ids: []}` | triggers SIM-01 for all candidate actions; async, poll or WebSocket |
| POST | `/recommendations/{id}/decision` | `{decision: "approve"\|"reject", reason?: string, override_action?: object}` | `200 Recommendation` | requires `controller`/`admin`; writes `audit_logs` |

## 5.7 Simulation

| Method | Path | Body | Response | Notes |
|---|---|---|---|---|
| POST | `/simulation/scenarios/{name}/run` | `{action?: object, seed?: int}` | `202 {simulation_run_id}` | ad-hoc what-if, not tied to a recommendation |
| GET | `/simulation/runs/{id}` | — | `SimulationRun` incl. `SimulationResult` when completed | |

## 5.8 Route rationalization / analytics

| Method | Path | Response |
|---|---|---|
| GET | `/analytics/routes/{route_id}/utilization?window=30d` | `{utilization_pct, overlap_pct, coverage_pct, avg_headway_s}` |
| GET | `/analytics/routes/{route_id}/recommendations` | `RouteRationalizationRecommendation[]` |
| GET | `/analytics/performance?window=7d` | `{on_time_pct, avg_wait_s, bunching_events, fleet_utilization_pct}` |
| GET | `/analytics/model-comparison?target=traffic` | comparison table used by doc 14 evaluation |

## 5.9 WebSocket

| Path | Direction | Payload |
|---|---|---|
| `/ws/live` | server → client | `{type: "vehicle_update"\|"alert"\|"recommendation", data: {...}}` |

Client subscribes once after auth; server pushes on every state change
relevant to the connected dashboard (fan-out from the Redis Streams consumer
in `services/api`).

## 5.10 Versioning

- Path-versioned (`/api/v1`); breaking changes get `/api/v2`, old version kept
  until all consumers (web app, telemetry client, simulation bridge) migrate.
- `model_version_id` is always included wherever a prediction or recommendation
  is returned, so clients/evaluation scripts can pin to a specific model run.

---
*v1.2 — Phase 0 baseline, §5.3a (Phase 2 / TASK-201 transportation network
endpoints) and the `/routes/{route_id}` row added in place, and §5.2/§5.3
annotated with TASK-204's actual telemetry/fleet implementation. See
[PHASE2_DESIGN.md](PHASE2_DESIGN.md) and
[TASK204_DESIGN.md](TASK204_DESIGN.md) for the reasoning.*
