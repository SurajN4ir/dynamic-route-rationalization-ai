# 14. Evaluation Methodology

This is what turns AURA from "a system that runs" into a thesis/SIH
submission with defensible results. No number in the final report should be
un-reproducible from this methodology — no hand-picked "it worked once" runs.

## 14.1 Research questions (from the project framing)

- **Primary:** Can a predictive, RL-based fleet control system improve
  public transport performance under dynamic traffic/demand conditions
  compared with fixed schedules and rule-based control?
- **Secondary:**
  1. Does predictive information (traffic/ETA/delay/demand/bunching)
     improve intervention quality over reactive-only control?
  2. Does RL outperform rule-based fleet control, and does PPO outperform DQN
     (or vice versa) for this environment?
  3. How does each strategy's performance degrade as disruption severity increases?
  4. Does digital-twin counterfactual evaluation change which action would
     have been chosen vs. picking the RL agent's top action blindly?
  5. Can historical demand analysis identify better route/frequency configurations?

## 14.2 Prediction model evaluation

For each of the five models (doc 07), compare the algorithm progression on
a common held-out test set (split by time, not randomly, to respect
temporal structure):

| Model | Candidates | Metrics |
|---|---|---|
| Traffic | historical average → XGBoost → LSTM/GRU → (optional GNN) | MAE, RMSE, MAPE per horizon (5/15/30/60 min) |
| ETA | naive (distance/avg speed) → XGBoost → LSTM | MAE, RMSE (minutes) |
| Delay | naive (route/time-slot base rate) → XGBoost → LSTM | Brier score, MAE (expected delay) |
| Demand | historical average by time-of-day → XGBoost → LSTM | MAE, RMSE |
| Bunching | rule threshold on headway → XGBoost → LSTM | precision, recall, F1, lead time (how early correctly flagged) |

Report a table per model, not just a headline number, and state sample size
and time range of the test set.

## 14.3 Fleet control strategy evaluation

Compare, on the same held-out scenario seeds (doc 08.6):

| Strategy | Description |
|---|---|
| Fixed timetable | no intervention |
| Rule-based | fixed heuristic thresholds (doc 08.5) |
| DQN | doc 08 |
| PPO | doc 08 |

**Metrics** (aggregated over the scenario set, mean ± std):
- average passenger waiting time
- average schedule delay
- bunching events per hour
- headway variance (stability)
- fleet utilization %
- operating cost proxy (vehicle-hours used for interventions)
- fuel/CO2 proxy (SUMO emission model output)

## 14.4 Stress testing

Vary disruption severity independently and re-run 14.3's comparison at each level:

- **Traffic multiplier:** 0%, +10%, +20%, +30%, +40%, +50% over baseline.
- **Injected events:** accident, road closure, demand spike, multiple
  simultaneous incidents (doc 09 §9.3).

Report where each strategy's performance degrades non-linearly or fails
outright (e.g. rule-based control breaking down under multi-incident
scenarios where RL still adapts, or vice versa) — the interesting result is
*where the gap changes*, not just the headline averages.

## 14.5 Routing evaluation

Compare, for `REROUTE_BUS` candidate generation:

| Strategy | Description |
|---|---|
| Shortest-distance | plain Dijkstra on static distance |
| Traffic-aware | Dijkstra/A* with live traffic-adjusted edge costs (doc 07 §7.1 output) |
| ML-enhanced | edge costs incorporating predicted (not just current) traffic |

**Metrics:** realized travel time, delay incurred, route deviation (extra
distance vs. shortest path).

## 14.6 Ablation studies

- Reward weight sensitivity (doc 08.4): retrain/evaluate with at least 2-3
  alternative weight configurations to show the recommendation isn't an
  artifact of one arbitrary weighting.
- Prediction-informed vs. reactive-only decision engine: run the rule-based
  and RL controllers with prediction inputs disabled (reacting only to
  current state) vs. enabled, to directly answer secondary research question 1.
- Counterfactual simulation vs. blind top-action: compare outcomes if the
  system always executed the RL agent's top-ranked action without SUMO
  validation vs. the full pipeline (doc 08.7) — quantifies the value of the
  digital-twin safety layer for secondary research question 4.

## 14.7 Reporting

- Every experiment referenced in the final report has an MLflow run id (or
  a batch of run ids for a sweep) and the exact scenario seed set used —
  traceable, not just a table pasted into a document.
- No fabricated or estimated metrics — if a comparison couldn't be run in
  time, the report says so explicitly rather than presenting a plausible
  guess as a result.

---
*v1.0 — Phase 0.*
