# 13. Testing Strategy

## 13.1 Pyramid

```
        ┌───────────────────────────┐
        │   Simulation scenario     │   fewest, slowest
        │   tests (SUMO end-to-end) │
        ├───────────────────────────┤
        │   RL policy tests         │
        ├───────────────────────────┤
        │   ML model tests          │
        ├───────────────────────────┤
        │   Integration tests       │
        ├───────────────────────────┤
        │   Unit tests              │   most, fastest
        └───────────────────────────┘
```

## 13.2 Unit testing

**Scope:** routing calculations (A*/Dijkstra correctness on known graphs),
feature engineering functions (doc 07 §7.7 — no leakage, correct
aggregation windows), reward function arithmetic (doc 08.4 given fixed
inputs), validation logic (doc 06.1 rules), API request/response schema
validation.

**Tools:** `pytest` for Python services/ml/rl; Vitest/Jest for `apps/web`.

**Bar:** every pure function in `ml/*/features.py`, `rl/rewards/reward.py`,
and the ingestion validators has direct unit tests with edge cases
(empty input, boundary values, malformed timestamps).

## 13.3 Integration testing

**Scope:** the full pipeline `telemetry → Redis → fusion → prediction →
decision → API → dashboard` (doc 03.4 data flow example), using
`docker-compose.ci.yml` (doc 11.4) against a seeded test database.

**Representative tests:**
- POST telemetry → assert it appears in `/fleet` within the NFR latency budget.
- POST the identical telemetry sample twice (same vehicle_id/ts/source) →
  assert exactly one `telemetry` row exists (doc 06 §6.1a idempotency).
- POST an out-of-order (older-timestamp) sample after a newer one → assert
  it lands in `telemetry` history but does **not** regress the cached
  current-state view (doc 06 §6.1b).
- Stop sending telemetry for a vehicle past `STALE_THRESHOLD_S` → assert a
  `telemetry_anomaly` (stale) event fires and `/fleet` marks it stale.
- Inject a synthetic bunching-risk state → assert an alert appears on
  `stream:events:bunching` and then in `/alerts`.
- Full recommendation flow → assert `/recommendations/{id}/simulate` then
  `/recommendations/{id}/decision` produces an `audit_logs` row.

**Tools:** `pytest` + `httpx` against the running compose stack, or
Playwright for browser-level flows through `apps/web`.

## 13.4 ML testing

**Scope, per model (doc 07):**
- **Data leakage:** a feature must never be computable from data timestamped
  after the prediction's target time (automated check on the feature
  pipeline, not just code review).
- **Prediction accuracy regression:** each model's held-out MAE/RMSE/MAPE
  (or precision/recall for bunching) must not regress beyond a configured
  tolerance vs. its last registered `model_versions` metrics — CI fails the
  `ml-eval` job (doc 11.4) if it does.
- **Edge cases:** missing feature values, a route with only one historical
  observation, a stop with zero historical demand.
- **Model drift:** a scheduled job compares live prediction error (once
  ground truth is observable, e.g. actual ETA vs. predicted) against the
  training-time metric; a sustained gap triggers a retraining flag (doc 10.10 MLOps).

## 13.5 RL testing

**Scope:**
- **Policy stability:** repeated evaluation runs (fixed seed) produce
  consistent action distributions — no wild nondeterminism beyond
  documented stochastic policy behavior.
- **Reward convergence:** training curves are logged (MLflow) and a
  regression test asserts the final N-episode average reward exceeds the
  fixed-timetable baseline on the training scenario set.
- **Unseen scenarios:** evaluation on scenario seeds never used in training
  (doc 08.6 train/test split by seed) — this is the actual generalization test.
- **Action validity:** every action the trained policy selects passes the
  constraint validator (doc 08.3) — a policy that tries to select a masked
  action is a test failure, not something silently corrected at inference time.
- **No oracle leakage:** state-vector prediction fields (doc 08 §8.4a)
  are populated from actual doc 07 model inference during training/eval,
  never from privileged SUMO ground truth — assert this by checking the
  environment never calls into SUMO's future-state accessors when building
  the prediction-derived portion of the observation.

## 13.6 Simulation testing

**Scope:** each scenario template (doc 09 §9.3 — normal, traffic_spike,
accident, road_closure, demand_surge, multi_incident) has at least one test
that runs it end-to-end and asserts:
- the SUMO run completes without error/deadlock,
- `simulation_results` are populated and internally sane (e.g.
  `avg_wait_s >= 0`, `bunching_events >= 0`),
- reproducibility (FR-SIM-02): same (scenario, action, seed) run twice
  produces matching results within floating-point tolerance.

## 13.7 What CI runs on every PR vs. on demand

| Suite | Trigger |
|---|---|
| Unit + lint + type check | every PR |
| Integration (compose-based) | every PR touching `services/`, `apps/web`, or `docs/architecture` schema docs |
| ML eval regression | every PR touching `ml/` |
| RL eval regression | every PR touching `rl/` |
| Full stress-test matrix (doc 14 §14.4) | manual/scheduled, ahead of Phase 11 reporting — too slow for per-PR CI |

---
*v1.0 — Phase 0.*
