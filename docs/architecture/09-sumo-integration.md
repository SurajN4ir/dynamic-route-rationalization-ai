# 9. SUMO Integration Architecture

## 9.1 Purpose

SUMO serves two distinct roles — keep them conceptually separate even though
they share the same network files:

1. **Live demo data source** — a running SUMO instance emits telemetry for
   50+ simulated buses through the same contract as phone GPS (doc 06),
   so the dashboard shows a full-size network even with only a few real
   phones reporting.
2. **RL training/evaluation environment and counterfactual engine** — SUMO is
   stepped programmatically via TraCI to train RL policies (doc 08) and to
   answer "what happens if we do X" for the recommendation engine (FR-SIM-01).

These are two different processes/configurations (a free-running simulation
vs. a controlled, resettable, seeded one), not the same SUMO instance doing
both jobs at once.

## 9.2 Network construction

```
OSM extract (bounded service area)
        ↓  osmnx / netconvert
SUMO network (.net.xml)
        ↓
Route/stop overlay (from routes/stops tables, doc 04)
        ↓
Bus route definitions (.rou.xml) + stop definitions (additional file)
        ↓
simulation/networks/<city>/  (versioned, not regenerated ad hoc)
```

Network files live under `simulation/networks/`, route/scenario files under
`simulation/routes/` and `simulation/scenarios/` (doc 10 repo layout).
Regeneration from OSM is a scripted, reproducible step
(`simulation/sumo/build_network.py`), never hand-edited XML.

## 9.3 Scenario library

Each scenario is a named, versioned config (traffic multiplier, demand
multiplier, injected incidents, closed edges) consumed by both the live-demo
runner and the RL/counterfactual runner:

| Scenario | Definition |
|---|---|
| `normal` | baseline traffic/demand curves |
| `traffic_spike` | traffic multiplier +X% on a subset of edges for a time window |
| `accident` | one edge capacity reduced to near-zero for a duration, at a configurable location |
| `road_closure` | one edge fully closed for a duration |
| `demand_surge` | demand multiplier +X% at one or more stops |
| `multi_incident` | composition of two or more of the above |

Scenarios are parameterized (edge id, magnitude, start/duration, seed) so
the same scenario name can generate many distinct evaluation instances —
required for the stress-test matrix in doc 14.

## 9.4 TraCI bridge

`services/simulation` owns the TraCI connection lifecycle:

```python
class SumoBridge:
    def start(self, scenario: ScenarioConfig, seed: int) -> None: ...
    def step(self, n: int = 1) -> None: ...
    def apply_action(self, action: Action) -> None: ...   # e.g. traci.vehicle.setSpeed for HOLD_BUS
    def get_state(self) -> NetworkState: ...               # feeds doc 08 state vector
    def get_metrics(self) -> SimulationResult: ...          # doc 04 simulation_results shape
    def close(self) -> None: ...
```

- `apply_action` maps each doc 08 action to concrete TraCI calls, e.g.
  `HOLD_BUS` → hold the vehicle at its current stop via
  `traci.vehicle.setStop(..., duration=hold_s)`; `REROUTE_BUS` →
  `traci.vehicle.setRoute(...)` with the alternate edge sequence from the
  routing engine (doc 03.3) — SUMO never invents a path itself.
- One `SumoBridge` instance per concurrent simulation run; counterfactual
  comparisons (FR-SIM-01, "run 4 candidates") run as independent instances
  (sequential or parallel worker pool), each seeded identically so only the
  action differs — this is what makes the comparison valid.
- **Concurrency is an in-process worker pool, not extra containers.** Each
  concurrent SUMO subprocess needs its own TraCI port; `services/simulation`
  owns a small pool (size = max concurrent candidate actions, v1 default 4,
  doc 05 §5.6) that allocates a free port per run and tears the subprocess
  down when the run completes. This must be explicit in the doc 11
  container (no extra `simulation` replicas needed for v1 scale) — a single
  container running N SUMO subprocesses internally, not N containers.

## 9.5 RL environment wrapper

`rl/environments/aura_env.py` wraps `SumoBridge` in a Gymnasium `Env`:

```python
class AuraEnv(gym.Env):
    def reset(self, *, seed=None, options=None) -> tuple[obs, info]: ...
    def step(self, action) -> tuple[obs, reward, terminated, truncated, info]: ...
    def action_masks(self) -> np.ndarray: ...   # from constraint engine, doc 08.3
```

`reset()` starts a fresh `SumoBridge` against a randomly (but seed-tracked)
sampled scenario instance from the library (9.3); `step()` applies the
chosen action, advances SUMO by the epoch duration, computes the doc 08
reward from the resulting `SimulationResult` vs. the `NO_ACTION` baseline
computed for the same epoch.

## 9.6 Telemetry bridge (live-demo mode)

A separate lightweight process (`apps/telemetry`'s SUMO adapter, or a script
under `simulation/sumo/`) polls a free-running SUMO instance via TraCI on a
fixed interval and POSTs each simulated bus's state to `/telemetry`
(doc 05.2) using the canonical contract (doc 06.1) with `source: "sumo"` —
this is intentionally the same HTTP path a phone client uses, not a
privileged internal API, so the rest of the system cannot tell the
difference (FR-INGEST-02).

This live-demo SUMO instance is a **long-running sidecar process, distinct
from `services/simulation`'s on-demand worker pool (§9.4)** — it isn't
started per-request, it runs for the duration of the demo. It needs its own
entry in doc 11's compose file (e.g. a `sumo-live-demo` service) separate
from the `simulation` service; doc 11 currently only lists the on-demand
`simulation` service and should be updated when Phase 3 builds this.

## 9.7 Performance considerations

- Counterfactual runs (FR-SIM-01 target: <30s wall clock for 4 candidates
  over a 10-min horizon) should use SUMO's non-GUI (`sumo`, not `sumo-gui`)
  binary in headless/batch mode, with `--step-length` tuned for speed vs.
  fidelity, and may run in parallel worker processes if single-instance
  timing doesn't meet the budget.
- Live-demo mode should run at a step length that produces visually
  reasonable bus movement on the dashboard (e.g. 1s simulated per ~1s wall
  clock, i.e. real-time factor ≈ 1), independent of the batch mode used for
  RL training.

---
*v1.0 — Phase 0.*
