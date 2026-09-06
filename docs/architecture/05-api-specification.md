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

| Method | Path | Body | Response | Notes |
|---|---|---|---|---|
| POST | `/telemetry` | `VehicleTelemetry` (doc 06) | `202 {status:"accepted"}` | Used by phone client + SUMO bridge |
| POST | `/telemetry/batch` | `VehicleTelemetry[]` | `202 {accepted, rejected[]}` | Rejected items include validation reason |
| POST | `/incidents` | `{type, lat, lon, severity, starts_at, ends_at?}` | `201 {incident_id}` | requires `controller`/`admin` role |
| GET | `/incidents?active=true` | — | `Incident[]` | |

## 5.3 Fleet / network state

| Method | Path | Response | Notes |
|---|---|---|---|
| GET | `/fleet` | `VehicleState[]` | current position, speed, delay, status, anomaly flags |
| GET | `/fleet/{vehicle_id}` | `VehicleState` | |
| GET | `/routes` | `Route[]` | |
| GET | `/routes/{route_id}/stops` | `Stop[]` | ordered |
| GET | `/trips/{trip_id}` | `Trip` incl. current ETA per remaining stop | |

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
*v1.0 — Phase 0.*
