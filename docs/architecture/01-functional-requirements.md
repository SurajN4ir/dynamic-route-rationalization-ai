# 1. Functional Requirements

IDs are stable identifiers to reference from code, tests, and PRs
(`FR-INGEST-01`, etc.). "Acceptance" is what Phase 11 evaluation must be able
to demonstrate — not aspirational, must be testable.

## FR-INGEST — Data ingestion

| ID | Requirement | Acceptance |
|---|---|---|
| INGEST-01 | System accepts vehicle telemetry (GPS, speed, heading, occupancy) from phone clients over HTTP, at up to 1 sample/5s per vehicle. | Load test sustains 200 vehicles × 1 sample/5s with p99 ingest latency < 500ms. |
| INGEST-02 | System accepts the same telemetry contract from a SUMO simulation bridge. | A SUMO run of 50 simulated buses produces telemetry indistinguishable in schema from INGEST-01. |
| INGEST-03 | System imports static GTFS-like data: routes, stops, trips, schedules. | A sample agency's routes/stops/trips load without manual transformation. |
| INGEST-04 | System imports OSM road network for a bounded metro area. | `osmnx` graph builds and is queryable via the routing service. |
| INGEST-05 | System accepts manually or externally reported incidents (accident, closure, breakdown) with location, time window, severity. | Incident appears in `incidents` table and is visible to the prediction/event engines within 5s. |
| INGEST-06 | Malformed or out-of-bounds telemetry (impossible speed, coordinates outside service area, timestamp skew) is rejected, not silently accepted. | Fuzzed bad-input test suite: 100% of defined invalid cases rejected with a structured error, 0% silently stored. |

## FR-FUSE — Data fusion / network state

| ID | Requirement | Acceptance |
|---|---|---|
| FUSE-01 | System maintains a single current-state view per vehicle (last known position, speed, delay, assigned trip) regardless of data source. | Querying vehicle state returns one record per vehicle_id, last-write-wins by timestamp. |
| FUSE-02 | System map-matches raw GPS to the road network. | ≥95% of telemetry points snap to a plausible edge within 25m on the test route set. |
| FUSE-03 | System computes derived state: headway between consecutive buses on a route, schedule adherence (delay), current segment speed vs. historical baseline. | Headway and delay values available via API for any active trip. |

## FR-PRED — Prediction engine

| ID | Requirement | Acceptance |
|---|---|---|
| PRED-01 | Traffic model predicts segment-level speed at +5/+15/+30/+60 min horizons. | MAE reported against held-out historical/SUMO data; beats historical-average baseline (see doc 14). |
| PRED-02 | ETA model predicts arrival time at each remaining stop for an active trip, with a prediction interval. | Reported MAE/MAPE; beats naive distance/avg-speed baseline. |
| PRED-03 | Delay model predicts probability of >10min delay and expected delay magnitude for an active trip. | Reported Brier score / MAE; beats baseline. |
| PRED-04 | Demand model predicts passenger count at stop level for the next 15/30 min. | Reported MAE; beats historical-average-by-time-of-day baseline. |
| PRED-05 | Bunching model predicts probability of two consecutive buses on the same route bunching (headway < threshold) within the next N minutes, plus expected time-to-bunching. | Reported precision/recall against labeled historical/SUMO bunching events. |
| PRED-06 | All predictions are versioned (model id + version) and timestamped. | Every prediction record in `predictions` table references a `model_versions` row. |

## FR-EVENT — Event engine

| ID | Requirement | Acceptance |
|---|---|---|
| EVENT-01 | System raises a bunching alert when bunching probability crosses a configurable threshold. | Alert appears in `/alerts` within 5s of the prediction crossing threshold. |
| EVENT-02 | System raises an incident-impact alert when an active incident intersects a route's path. | Alert references the incident and affected route/trip ids. |
| EVENT-03 | System flags GPS/telemetry anomalies (dropout > N seconds, teleport, stale data) per vehicle. | Anomaly flag visible on `/fleet` for the affected vehicle. |

## FR-DEC — Decision engine

| ID | Requirement | Acceptance |
|---|---|---|
| DEC-01 | Given a triggering condition (bunching risk, delay, incident), the decision engine enumerates feasible candidate actions from the action space (doc 08) respecting operational constraints (vehicle availability, route feasibility, min/max hold time). | For a given scenario, the candidate list contains only actions that pass constraint validation; infeasible actions (e.g. dispatching a spare that doesn't exist) never appear. |
| DEC-02 | A rule-based controller (baseline) can independently produce a recommendation without RL, for use as an evaluation baseline and a fallback if the RL service is unavailable. | System functions (degraded) with RL service down. |
| DEC-03 | An RL agent (DQN and, later, PPO) proposes the ranked-best action given current state. | RL service returns an action + Q-value/score within 1s of a state query in the demo environment. |

## FR-SIM — Simulation / counterfactual engine

| ID | Requirement | Acceptance |
|---|---|---|
| SIM-01 | For a given scenario and a set of candidate actions (including "do nothing"), the system runs each through the SUMO digital twin and returns predicted outcome metrics (avg wait, avg delay, bunching count, fuel/CO2 proxy). | Running 4 candidate actions for one scenario completes within an operator-tolerable time budget for the demo (target: < 30s wall clock for a 10-minute simulated horizon). |
| SIM-02 | Simulation runs are reproducible given the same scenario + seed. | Re-running the same (scenario, action, seed) produces outcome metrics within floating-point tolerance. |
| SIM-03 | System supports named scenario templates: normal, traffic spike, accident, road closure, demand surge, multi-incident. | Each template is loadable by name and produces a valid SUMO run. |

## FR-REC — Recommendation engine

| ID | Requirement | Acceptance |
|---|---|---|
| REC-01 | System ranks simulated candidate actions and selects a best recommendation with a human-readable explanation (cause, expected impact, confidence). | Recommendation object includes `action`, `reason`, `expected_impact`, `confidence`, `alternatives[]`. |
| REC-02 | Controller can approve, reject, or override a recommendation; the decision and a free-text reason are persisted. | `audit_logs` contains an entry for every recommendation shown, with outcome (approved/rejected/expired) and timestamp. |
| REC-03 | An approved recommendation's real-world outcome (once observed) is linked back to the original recommendation for feedback/evaluation. | Given a recommendation id, system can report predicted vs. actual outcome. |

## FR-ROUTE — Route rationalization (long-horizon)

| ID | Requirement | Acceptance |
|---|---|---|
| ROUTE-01 | System computes per-route utilization, overlap with other routes, and demand coverage from historical data. | Report generated per route with utilization %, overlap %, coverage %. |
| ROUTE-02 | System recommends frequency changes (increase/decrease buses/hour) for routes crossing over/under-utilization thresholds. | Recommendation includes current vs. proposed frequency and expected effect on crowding/coverage. |

## FR-UI — Dashboards

| ID | Requirement | Acceptance |
|---|---|---|
| UI-01 | Controller dashboard shows live map of all vehicles with status, plus active alerts and pending recommendations. | Map updates within 5s of new telemetry via WebSocket, no manual refresh. |
| UI-02 | Controller can open a recommendation, trigger "simulate", and see comparative outcome metrics for each candidate action before approving. | UI round-trips to SIM-01 and renders a comparison table/chart. |
| UI-03 | Analytics views expose historical performance (on-time %, bunching events, avg wait) and model comparison results (doc 14). | Charts render from `simulation_results`/`predictions` history, not hardcoded data. |
| UI-04 | Passenger-facing view (secondary, built after controller platform) shows bus location, ETA, and crowding prediction for a selected route/stop. | ETA and crowding shown for at least one live route in the demo. |

## Out of scope for v1

- Payment/ticketing integration.
- Multi-agency federation (single agency/network per deployment).
- Full multi-agent RL (single-agent RL is the v1 target; multi-agent is a stretch goal per doc 08).
- Mobile native apps (web-responsive only for v1).

---
*v1.0 — Phase 0. Amend deliberately; see [README](README.md#change-control).*
