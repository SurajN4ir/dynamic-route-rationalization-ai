# 7. ML Model Contracts

Each model is a separate artifact under `ml/<name>/`, tracked via MLflow
(experiment + run) and DVC (data/artifact versioning), registered in the
`model_versions` table (doc 04). This document fixes the **input/output
contract** each model must honor regardless of which algorithm implements it
(historical-average → XGBoost → LSTM progression per model, doc 14) — the
serving layer (`services/prediction`) depends only on this contract, not on
model internals.

**Common envelope:** every model's output below shows only its
target-specific fields. In the actual API/event/table response, those
fields are wrapped with `model_version_id` and `generated_at` (populated by
`services/prediction`, not by the model itself — see §7.6) — e.g. the
bunching model's real response is the §7.5 object plus those two fields,
which is what makes it identical to the `stream:events:bunching` payload in
doc 06 §6.3 (that stream additionally carries `event_type`, added by the
event engine, not the model). Doc 05's "response shapes match doc 07
exactly" means *target fields + common envelope*, not the bare examples below.

## 7.1 Traffic model (`ml/traffic`)

**Input features**
| Feature | Source |
|---|---|
| `edge_id` | OSM road graph |
| `current_speed_mps` | fused telemetry, rolling window |
| `historical_speed_by_time_of_day` | `traffic_observations` aggregate |
| `time_of_day`, `day_of_week` | derived |
| `neighboring_edge_speeds` | adjacent edges in road graph |
| `active_incident_on_edge` | `incidents` |
| `weather_condition` (optional, if data available) | external static/historical |

**Output**
```json
{
  "edge_id": "string",
  "horizon_s": 300,
  "predicted_speed_mps": 6.2,
  "confidence_interval": [4.8, 7.6]
}
```

**Baselines to compare (doc 14):** historical average → XGBoost → LSTM/GRU → (optional) GNN.

## 7.2 ETA model (`ml/eta`)

**Input:** `trip_id`, current position/segment, current speed, per-remaining-edge traffic prediction (7.1), stops remaining, current schedule delay, time of day/day of week, historical segment travel times.

**Output**
```json
{
  "trip_id": "uuid",
  "stop_id": "uuid",
  "predicted_arrival": "2026-09-06T10:28:00Z",
  "eta_minutes": 13.0,
  "confidence_interval_minutes": [11.0, 15.0]
}
```

## 7.3 Delay model (`ml/delay`)

**Input:** same feature family as ETA model, plus historical delay distribution for this route/time slot.

**Output**
```json
{
  "trip_id": "uuid",
  "probability_delay_gt_10min": 0.84,
  "expected_delay_s": 620
}
```

## 7.4 Demand model (`ml/demand`)

**Input:** `stop_id`, time of day/day of week, historical boarding/alighting (`demand_observations`), nearby event/holiday flags (optional), recent trend (last N observations).

**Output**
```json
{
  "stop_id": "uuid",
  "horizon_s": 900,
  "predicted_demand": 44,
  "capacity": 40,
  "overcapacity_probability": 0.78
}
```

## 7.5 Bunching model (`ml/bunching`)

**Input:** for each consecutive vehicle pair on a route: current headway (time and distance), headway trend (last N minutes), each vehicle's current delay, upstream traffic prediction (7.1), upstream demand prediction (7.4, higher demand → longer dwell → higher bunching risk).

**Output** — matches the event contract in doc 06 §6.3:
```json
{
  "route_id": "uuid",
  "leading_vehicle_id": "uuid",
  "trailing_vehicle_id": "uuid",
  "probability": 0.86,
  "expected_time_to_bunch_s": 480
}
```

## 7.6 Common serving contract

All five models are served behind `services/prediction` with a uniform
inference interface so the decision engine and API layer don't special-case
per model:

```python
class Predictor(Protocol):
    def predict(self, features: dict) -> dict: ...
    @property
    def model_version_id(self) -> str: ...
```

Every response written to the `predictions` table includes
`model_version_id`, `target_type`, `target_ref_id`, `horizon_s`,
`generated_at` (doc 04) — no model is allowed to skip versioning, since
FR-PRED-06 and the evaluation methodology (doc 14) both depend on it.

## 7.7 Feature store note

v1 does not require a dedicated feature-store product. Features are computed
by shared functions in `ml/<name>/features.py` per model, reading from
Postgres/Redis directly, with unit tests guaranteeing no leakage (e.g. a
traffic feature must never read a `traffic_observations` row timestamped
after the prediction's `generated_at`). Revisit only if duplicated feature
logic across models becomes a real maintenance problem.

---
*v1.0 — Phase 0.*
