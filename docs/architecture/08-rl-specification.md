# 8. RL State / Action / Reward Specification

This document formalizes the MDP that `rl/` implements. The environment is
SUMO via TraCI (doc 09); the state is built from the prediction engine's
output (doc 07), not raw GPS — RL never re-learns what the ML models already
compute (component-architecture layering rule, doc 03.3).

## 8.1 MDP framing

- **Agent:** one fleet-control policy per route-cluster (v1: single-agent,
  single route or small route group under one controller's authority; doc
  01 explicitly defers full multi-agent RL to a stretch goal).
- **Decision epoch:** triggered by an event (bunching risk crosses threshold,
  incident detected, delay probability crosses threshold) or a fixed tick
  (e.g. every 60s) — not a fixed timestep game loop, since most of the time
  `NO_ACTION` is correct and we don't want the agent overfitting to acting
  every step.
- **Episode:** one simulated service period (e.g. a 2-hour peak window) in
  SUMO, ending at a fixed sim-time horizon or on an unrecoverable failure
  state (e.g. total network gridlock in the scenario).

## 8.2 State vector

All fields are numeric after encoding; categorical/one-hot noted.

| Group | Field | Encoding |
|---|---|---|
| Per active vehicle (k nearest to decision point, padded/masked) | position along route (0-1 normalized) | float |
| | speed (mps) | float |
| | current delay (s) | float |
| | occupancy / capacity ratio | float |
| | headway to leading vehicle (s) | float |
| | headway to trailing vehicle (s) | float |
| Predictions (doc 07) | predicted traffic speed on next edge | float |
| | predicted demand at next stop | float |
| | bunching probability with adjacent vehicle | float |
| | delay probability (>10min) | float |
| Incidents | active incident on route (binary) | 0/1 |
| | incident severity | one-hot {none, low, medium, high} |
| Fleet | number of available spare vehicles | int |
| | time since last intervention on this route | float (s) |
| Time context | time of day | sin/cos encoded |
| | day of week | one-hot |

Fixed-size vector via padding to `k` tracked vehicles (k configurable,
default 6 — the leading/trailing pair plus local neighbors); mask flag per
slot for "not present." Exact `k` and final dimensionality are an
implementation decision made in `rl/environments/`, recorded there, not
hardcoded twice.

## 8.3 Action space (discrete, v1)

| Action | Params | Precondition (validated by constraint engine, FR-DEC-01) |
|---|---|---|
| `NO_ACTION` | — | always valid |
| `HOLD_BUS` | `vehicle_id`, `hold_s` (bounded, e.g. 30-180s) | vehicle currently at/approaching a stop; hold_s within configured max |
| `RELEASE_BUS` | `vehicle_id` | vehicle currently held |
| `REROUTE_BUS` | `vehicle_id`, `alt_path_id` | alt path exists in road graph, is drivable by a bus, does not skip mandatory stops without a `SHORT_TURN` |
| `DISPATCH_SPARE` | `spare_vehicle_id`, `route_id`, `insertion_point` | a spare is available and idle |
| `SHORT_TURN` | `vehicle_id`, `turn_back_stop_id` | turn-back point is a valid designated short-turn stop for the route |
| `ADJUST_FREQUENCY` | `route_id`, `delta_buses_per_hour` | within fleet size / driver availability constraints |

**Discrete encoding.** The table above lists seven *action types*, but five
of them take parameters (`vehicle_id`, `hold_s`, `alt_path_id`, ...) — a
plain `Discrete(7)` space is not actually well-formed until every
parameterized action is flattened into its own index. v1 does this by
enumerating over the same fixed `k` tracked-vehicle slots used in the state
vector (§8.2) and a small fixed bucket set per continuous-ish parameter,
giving a bounded `Discrete(N)`:

```
N = 1                                  # NO_ACTION
  + k * len(HOLD_BUCKETS)              # HOLD_BUS(slot_i, bucket_j), e.g. 4 buckets: 30/60/120/180s
  + k                                  # RELEASE_BUS(slot_i)
  + k * MAX_ALT_PATHS                  # REROUTE_BUS(slot_i, alt_path_k), alt paths capped/ranked by the routing engine
  + MAX_SPARES * MAX_INSERTION_POINTS  # DISPATCH_SPARE(spare_i, insertion_j)
  + k * MAX_SHORT_TURN_POINTS          # SHORT_TURN(slot_i, turnback_j)
  + len(FREQ_DELTA_BUCKETS)            # ADJUST_FREQUENCY(delta_bucket), route is fixed per agent (§8.1)
```

Exact bucket counts and `MAX_*` caps are an `rl/environments/aura_env.py`
config constant (not re-derived ad hoc), and must be small enough to keep
`N` in the low hundreds — a combinatorial space in the thousands defeats
the point of using DQN (tabular-ish Q-value-per-action) and should push
toward a parameterized/hybrid action architecture instead (flag this during
Phase 6 if the numbers don't stay small once `k` and the bucket counts are
fixed).

Action masking: at each decision epoch, the constraint engine computes a
boolean mask of length `N` over this flattened space before it reaches the
agent, so the agent is never trained or evaluated against physically
infeasible actions (FR-DEC-01). This is exposed as the Gym-style
environment's `action_mask()` / `action_masks()` (doc 09 §9.5), not left to
the agent to learn by penalty.

**Library note (blocks Phase 6, needs a decision — see review):**
Stable-Baselines3's stock `PPO` and `DQN` do **not** support hard action
masking out of the box. Options: (a) PPO via `sb3-contrib`'s `MaskablePPO`
(supports masking natively) paired with a **custom-wrapped** DQN that
applies the mask by setting masked Q-values to `-inf` before `argmax` at
both training and inference time (stock SB3 `DQN` has no built-in hook for
this — it has to be subclassed or the mask applied at the policy-call
boundary); or (b) drop hard masking and use a large invalid-action penalty
instead for both algorithms, accepting that the agent must learn feasibility
rather than have it enforced — which weakens the FR-DEC-01 guarantee unless
the *downstream* constraint validator (doc 03.3) still filters the agent's
output before it ever reaches simulation/recommendation. Recommendation:
(a), with the constraint validator kept as a second, authoritative filter
regardless — never rely on the learned policy alone to respect constraints
end-to-end.

## 8.4 Reward function

```
R = - w1 * avg_passenger_wait_delta
    - w2 * avg_delay_delta
    - w3 * bunching_events_delta
    - w4 * fuel_proxy_delta
    - w5 * operating_cost_delta
    - w6 * route_deviation_penalty
    + w7 * on_time_performance_delta
    + w8 * coverage_delta
    + w9 * headway_stability_delta
```

- **Deltas are step-local, not a re-run counterfactual.** "Delta" here means
  the change in each metric between the epoch just simulated and a short
  trailing baseline window (e.g. the same route's rolling average over the
  last few epochs), read directly off the single SUMO rollout TraCI just
  advanced (doc 09 §9.5 `step()`). It is *not* the recommendation engine's
  full dual-run "simulate this action vs. simulate `NO_ACTION` from the same
  state" comparison (doc 09 §9.4) computed at every training step — doing
  that would mean every environment `step()` requires two full SUMO
  sub-rollouts, which does not scale to the number of steps DQN/PPO need to
  converge. The expensive dual-run counterfactual (doc 08.7, doc 14 §14.6)
  stays reserved for: (a) the human-facing recommendation engine, evaluated
  once per real trigger, and (b) periodic *evaluation* of a trained policy
  (doc 14), not for computing the per-step training reward.
- Weights `w1..w9` live in `rl/rewards/weights.yaml`, not hardcoded in
  training code. Sections 19-20 of the original design brief are explicit
  that "exact reward weights will be an experiment, not arbitrary numbers
  hidden in the code" — treat weight selection itself as a documented
  ablation in doc 14, not a one-time guess.
- Small negative cost on every non-`NO_ACTION` action to discourage
  over-intervention when the net benefit is marginal.

### 8.4a Training-time oracle leakage risk

The state vector (§8.2) includes model *predictions* (predicted traffic
speed, predicted demand, bunching probability, delay probability). Because
training happens inside SUMO, it is tempting — and easy by accident — to
populate those state fields by reading SUMO's actual future ground truth
directly (SUMO knows exactly what will happen next in its own simulation)
instead of running real inference through the doc 07 models. That produces
a policy trained with perfect foresight it will never have at real-world
inference time (doc 07 models are always imperfect estimates), so it learns
to over-trust "predictions" and transfers poorly. **Requirement:** during
both training and evaluation, state predictions must come from actual
inference through a doc 07 model (a frozen checkpoint is fine — it doesn't
need to be the latest version) run against the SUMO-simulated telemetry
stream exactly as it would run against real telemetry, never from
privileged SUMO internals. Covered by an explicit RL test (doc 13 §13.5).

### 8.4b Reward-hacking risks to monitor

- **Micro-holding for headway-stability credit:** an agent could spam short
  `HOLD_BUS` calls to nudge `headway_stability_delta` positive while net
  passenger wait gets worse. Mitigation: track each reward component
  separately in evaluation (doc 14 §14.3), not just the scalar sum — a
  policy that wins on the scalar but regresses `avg_passenger_wait_delta`
  is a hacking signal, not a good policy.
- **Frequency-churn gaming:** `ADJUST_FREQUENCY` affects simulated
  `fleet_utilization_pct`/`operating_cost_delta` without SUMO necessarily
  modeling real constraints (driver shift limits, depot capacity) that
  don't exist in the twin. Mitigation: constraint validator (§8.3) caps
  `delta_buses_per_hour` and change frequency per episode; treat any policy
  that relies heavily on `ADJUST_FREQUENCY` in evaluation as a flag to
  check the constraint bounds, not a win to report uncritically.

## 8.5 Algorithm progression

| Stage | Approach | Purpose |
|---|---|---|
| Baseline 1 | Fixed timetable (no intervention ever) | floor performance |
| Baseline 2 | Rule-based controller (e.g. `IF bunching_prob > 0.7: HOLD trailing bus`) | strong, explainable baseline; also the FR-DEC-02 fallback controller |
| RL 1 | DQN | discrete action space fits naturally; simpler to train/debug first |
| RL 2 | PPO | compare on-policy vs off-policy performance |
| Stretch | Multi-agent RL | only attempted once single-agent DQN/PPO is validated (doc 01, out-of-scope note) |

`rl/agents/` holds one module per algorithm; `rl/evaluation/` runs all four
(baseline 1, baseline 2, DQN, PPO) through the same evaluation harness (doc
14) so comparisons are apples-to-apples.

## 8.6 Training protocol

- Environment: `rl/environments/aura_env.py`, a Gymnasium-compatible wrapper
  around the SUMO/TraCI bridge (doc 09).
- Training scenarios drawn from the scenario library (doc 09 §9.3) with
  randomized traffic/demand seeds per episode to avoid overfitting to one
  fixed disruption pattern.
- Train/validation/test split is by **scenario seed**, not by time slice of
  a single run, so the test set is genuinely unseen disruption patterns.
- Stopping criteria: reward plateau over N episodes (config), plus a hard
  episode cap to keep training time bounded for the project timeline.
- Every training run is an MLflow experiment (params: algorithm, reward
  weights, hyperparameters; metrics: episode reward, eval-scenario
  performance deltas vs. baselines).

## 8.7 Safety wrapper (why RL never acts directly)

```
RL agent → candidate action (ranked)
        → constraint validator (8.3 preconditions)
        → SUMO counterfactual simulation (doc 09)
        → outcome estimate
        → recommendation engine (only humans approve, doc 01 FR-REC-02)
```

The RL policy's output is always a *candidate*, never an executed action —
this is the same human-in-the-loop guarantee as doc 01/02.9, and it's also
what makes the DQN vs. PPO research question (doc 14) answerable without
risking the live/simulated fleet on an untested policy update.

---
*v1.0 — Phase 0.*
