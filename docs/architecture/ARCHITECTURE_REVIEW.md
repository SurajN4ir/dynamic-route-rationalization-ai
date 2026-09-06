# AURA Phase 0 Architecture Review

**Reviewer role:** Senior/Principal Solution Architect (formal Phase 0 gate review)
**Scope:** all files under `docs/architecture/` (01-15 + README)
**Date:** 2026-09-06
**Review type:** documentation-only. No application code exists yet; nothing here blocks on runtime behavior, only on internal consistency and buildability of the plan.

## Overall verdict: **APPROVED WITH CHANGES**

The architecture is coherent, appropriately layered (prediction / decision /
routing / simulation kept separate, per doc 03.3), and free of any load-bearing
paid dependency. It is buildable in stages exactly as doc 12 lays out. It was
**not** approved outright because the review found one critical RL-design gap
(a parameterized action space described as if it were a plain `Discrete(7)`)
and several concrete cross-document inconsistencies that would have surfaced
as real implementation bugs in Phase 4–7 if left uncorrected. All findings
below marked **[FIXED]** have already been corrected in the docs as part of
this review; the rest require a human decision and are listed in §12.

---

## 1. Critical issues

### C1 — RL discrete action space was underspecified for a combinatorial action set — **[FIXED, doc 08 §8.3]**
Five of the seven action types (`HOLD_BUS`, `REROUTE_BUS`, `DISPATCH_SPARE`,
`SHORT_TURN`, `ADJUST_FREQUENCY`) take parameters (which vehicle, how long,
which alternate path, etc.). The original doc 08 §8.3 listed them as if
"7 actions" were a valid `Discrete(7)` space for DQN — it is not; DQN and
PPO's discrete heads need one output per *fully enumerated* (action, params)
combination. Left unresolved, Phase 6 would have hit this the moment someone
tried to actually instantiate the Gym action space.
**Fix applied:** doc 08 §8.3 now defines an explicit flattening formula
bounded by the same `k` (tracked-vehicle count) already used in the state
vector, plus small fixed parameter buckets, keeping `N` in the low hundreds.

### C2 — Action masking is assumed but the chosen RL library doesn't support it out of the box — **[FIXED — flagged, decision required]**
Doc 08 required hard action masking (§8.3) and doc's tech stack (root README
context) names Stable-Baselines3 for DQN + PPO. Stock SB3 `PPO` and `DQN` do
not support action masking natively. This is a real blocker for Phase 6 if
not resolved before implementation starts.
**Fix applied:** doc 08 §8.3 now states the two viable paths (`sb3-contrib`
`MaskablePPO` + a custom-masked DQN wrapper, vs. penalty-based soft masking
with the constraint validator as an authoritative second filter) and
recommends the first. **This is still a decision for a human to confirm**
before Phase 6 (see §12).

---

## 2. Major issues

### M1 — `predictions.target_ref_id` typed `uuid` cannot hold an OSM edge id — **[FIXED, doc 04 §4.2]**
Traffic predictions target an OSM `edge_id` (a string, per doc 07 §7.1's own
output example: `"edge_id": "string"`), not a UUID. The column was typed
`uuid`, which would reject every traffic prediction write. Retyped to `text`
with a note documenting which target_types use which kind of ref.

### M2 — `route_stops` primary key allowed two stops at the same sequence position — **[FIXED, doc 04 §4.2]**
PK was `(route_id, stop_id, sequence)`. That doesn't prevent
`(route_A, stop_X, seq=3)` and `(route_A, stop_Y, seq=3)` from coexisting —
i.e. it doesn't actually enforce "one stop per position." Changed PK to
`(route_id, sequence)`, with `stop_id` as an indexed non-unique column
(loop routes may legitimately revisit a stop at a different sequence).

### M3 — Doc 07's model output examples didn't match doc 05's "matches doc 07 exactly" claim, or doc 06's own bunching event — **[FIXED, doc 07 intro]**
Doc 06 §6.3's bunching event includes `model_version_id` and `generated_at`;
doc 07 §7.5 said its output "matches the event contract in doc 06 §6.3" but
its own example omitted both fields (and all five models' examples omitted
them, despite §7.6 requiring them on every persisted prediction). Doc 05
then claimed API responses "match doc 07 exactly," which was false as
written. Fixed by adding an explicit common-envelope clause to doc 07: every
model's real output is its target fields *plus* `model_version_id` +
`generated_at`, added by the serving layer — the bare examples show target
fields only. This makes doc 05/06/07 mutually consistent without having to
edit five duplicate JSON blocks.

### M4 — No spatial or lookup indexes were specified anywhere — **[FIXED, doc 04 new §4.3]**
The data model named PostGIS as the reason for using Postgres but never
specified a single GIST index, despite FR-FUSE-02 (map-matching) and
FR-ROUTE-01 (route overlap) being spatial-query-heavy. Also missing:
time-series indexes for `traffic_observations`/`demand_observations`
(doc 07 feature lookups), a `predictions` "latest for target" index, and a
`recommendations(status, created_at)` index for the exact query doc 05
§5.6 defines (`/recommendations?status=pending`). Added a full indexes table.

### M5 — No idempotency mechanism for telemetry — **[FIXED, doc 04 §4.2, doc 06 §6.1a]**
A retried POST (phone/SUMO bridge recovering from a timeout) had no
protection against creating a duplicate `telemetry` row, which would corrupt
speed/headway aggregation and double-count into `traffic_observations`
sample counts. Added a unique constraint on `(vehicle_id, ts, source)` plus
an explicit `ON CONFLICT DO NOTHING` ingestion rule.

### M6 — Out-of-order telemetry and "stale GPS" had no defined handling — **[FIXED, doc 06 §6.1b]**
FR-FUSE-01 said "last-write-wins by timestamp" but never stated the rule
that makes that true (ignore late-arriving *older* samples for the live
cache, but still record them in history), and FR-EVENT-03's dropout
threshold (`N seconds`) was never given a value. Added the explicit rule and
a default `STALE_THRESHOLD_S = 15s`.

### M7 — RL reward formula, read literally, would require two full SUMO reruns per training step — **[FIXED, doc 08 §8.4]**
§8.4 said reward deltas are computed "the same way the simulation engine
computes it for human-facing recommendations" (doc 09 §9.4's dual-run
NO_ACTION-vs-action comparison). Taken literally, every RL training step
would need two full SUMO sub-rollouts — DQN/PPO need on the order of
hundreds of thousands to millions of steps to converge, so this would make
training computationally infeasible on the ₹0/local-hardware budget the
whole project depends on. Fixed by clarifying that training-time reward uses
step-local metric deltas against a rolling baseline (cheap, from the single
live rollout), and reserving the expensive dual-run counterfactual for the
human-facing recommendation engine and periodic policy evaluation only.

### M8 — Training-time "oracle leakage" risk in the RL state vector — **[FIXED, doc 08 §8.4a, doc 13 §13.5]**
The state vector includes model *predictions* (traffic, demand, bunching,
delay). Because training runs inside SUMO, it's easy to accidentally
populate those fields from SUMO's actual future ground truth instead of real
model inference — training a policy with foresight it will never have at
real inference time, which would not transfer and would invalidate the
DQN/PPO evaluation results in doc 14. Added an explicit requirement (state
predictions must come from real doc 07 model inference, frozen checkpoint OK)
and a corresponding RL test.

### M9 — Parallel counterfactual simulation had no concurrency model in the container architecture — **[FIXED, doc 09 §9.4]**
Doc 09 said candidate actions "run as independent instances (sequential or
parallel worker pool)" but doc 11's docker-compose showed exactly one
`simulation` service with no notion of a worker pool, and each concurrent
SUMO/TraCI subprocess needs its own port. Clarified: this is an in-process
worker pool inside the single `simulation` container (port-per-run,
default 4 concurrent), not extra container replicas.

### M10 — Live-demo SUMO instance had no owning process/service — **[FIXED, doc 09 §9.6]**
Doc 09 §9.1 correctly distinguishes "live-demo SUMO" from "on-demand
counterfactual/training SUMO," but no service in doc 10/11 actually owns a
long-running live-demo SUMO process — only the on-demand `simulation`
service exists. Flagged explicitly as a Phase 3 gap: needs its own
long-running sidecar entry in doc 11, distinct from the on-demand
`simulation` service.

### M11 — Map tile source unspecified, silent risk to the ₹0 principle — **[FIXED, doc 15 §15.4a]**
`apps/web`'s MapLibre needs a tile source; none of the 15 docs named one.
Left implicit, this defaults to whatever the implementer reaches for first
(often a third-party hosted tile service with its own usage limits/pricing),
quietly violating doc 01 Rule 3. Added a default plan (self-hosted tiles
from the same OSM extract already required for routing) as an explicit open
item to close before Phase 3.

---

## 3. Minor issues

- **Model-version identifier ambiguity [FIXED, doc 04]** — `model_versions.version` said "semantic or MLflow run id," which is ambiguous for the traceability doc 14 §14.7 depends on. Now canonically the MLflow run id.
- **Training/serving boundary not stated explicitly** — doc 11 mounts `./ml:/app/ml:ro` into the prediction service, correctly implying training happens outside the serving container, but this is never stated as a rule. Low risk, no fix applied — worth a one-line addition in doc 07 or doc 11 whenever Phase 4 scaffolding is written, not urgent enough to edit now.
- **Phone telemetry auth model is awkward** — doc 05 requires JWT bearer auth on every write endpoint including `/telemetry`, implying a phone client needs a full user login rather than a lightweight per-device token. Not fixed (it's a design choice, not an inconsistency) — flagged for Phase 3 design refinement in §12.
- **Map-matching algorithm unspecified** — FR-FUSE-02 states a 95%-within-25m target but doc 09 never names the matching approach (nearest-edge snap vs. HMM-based map matching). Not fixed — implementation-level detail appropriate to decide in Phase 2/3, not Phase 0.
- **WebSocket reconnection/backpressure behavior undefined** — doc 05 §5.9 defines the payload shape but not reconnect/replay or slow-consumer handling. Not fixed — low risk at demo scale (doc 02.2), worth one line whenever Phase 3 implements it.
- **"Decision Engine" (prose) vs. `services/optimization` (code) naming drift** — mapped once in doc 03 §3.2 but not repeated elsewhere; purely a recall nit, not a contradiction. No fix applied.

---

## 4. Cross-document consistency matrix

| Pair | Status | Notes |
|---|---|---|
| Requirements ↔ architecture | ✅ Consistent | Every FR in doc 01 maps to a named component in doc 03; doc 03.4's data-flow example exercises FR-EVENT/DEC/SIM/REC end to end. |
| Architecture ↔ database | ✅ Consistent after fixes | M1/M2/M4 were real gaps, now closed. |
| Database ↔ APIs | ✅ Consistent after fix | M3's envelope mismatch was the one real gap. |
| APIs ↔ Redis event contracts | ✅ Consistent | `/alerts`, `/recommendations`, WS payload all trace to a specific stream in doc 06. |
| ML contracts ↔ prediction service | ✅ Consistent after fix | M3; §7.6's `Predictor` protocol matches `services/prediction`'s stated responsibility in doc 03.2. |
| RL specification ↔ SUMO environment | ✅ Consistent after fixes | C1/C2/M7/M8 were real gaps between doc 08's MDP framing and doc 09's actual TraCI mechanics; now reconciled. |
| SUMO ↔ simulation APIs | ✅ Consistent after fix | M9; FR-SIM-01's "4 candidates in <30s" now has a stated concurrency mechanism. |
| Docker services ↔ repository structure | ✅ Consistent | doc 10's six services match doc 11's compose file 1:1; M10 notes one missing *future* service (live-demo SUMO), not a contradiction with what exists today. |

---

## 5. RL-specific findings summary

| # | Finding | Severity | Status |
|---|---|---|---|
| C1 | Parameterized actions not flattened into a valid discrete space | Critical | Fixed |
| C2 | SB3 stock PPO/DQN lack native action masking | Critical | Flagged — decision needed |
| M7 | Reward formula implied a per-step double-SUMO-rerun | Major | Fixed |
| M8 | Oracle leakage risk from SUMO ground truth into state | Major | Fixed |
| — | Reward-hacking risks (micro-holding, frequency churn) | Minor/monitoring | Documented, doc 08 §8.4b |
| — | DQN appropriateness | Assessed | Appropriate *once* the action space is properly flattened and bounded (C1 fix) — DQN's off-policy sample efficiency suits the low-hundreds discrete space described. |
| — | PPO compatibility | Assessed | Compatible with the discrete/flattened space; masking support requires `sb3-contrib` (C2). |
| — | Operational feasibility of actions | Assessed | Sound in principle (constraint validator + doc 09 TraCI mapping for each action type), contingent on C1's flattening being implemented as specified. |
| — | State/action/reward circularity | Assessed | None found beyond M8 (which is a leakage risk, not circularity) — reward is computed from simulation outcomes, not fed back into the same-step state. |
| — | Buildable without paid APIs | Assessed | Yes — SUMO + TraCI + Gymnasium + local training, no paid dependency. |

---

## 6. Database-specific findings summary

| # | Finding | Severity | Status |
|---|---|---|---|
| M1 | `target_ref_id` typed uuid, needs text for edge ids | Major | Fixed |
| M2 | `route_stops` PK didn't prevent duplicate-sequence bug | Major | Fixed |
| M4 | No spatial/lookup indexes specified | Major | Fixed |
| M5 | No telemetry idempotency constraint | Major | Fixed |
| Minor | `model_versions.version` ambiguous | Minor | Fixed |
| — | Normalization | Assessed | Reasonable 3NF-ish design overall; jsonb used deliberately (doc 04 §4.4) for genuinely polymorphic fields (`predictions.value`, `recommendations.explanation`), not as a normalization shortcut — appropriate use. |
| — | Time-series telemetry storage | Assessed | Plain indexed table is right-sized for the stated scale (doc 02.2, ≤100 vehicles); hypertable/partitioning correctly deferred, not needed for v1 — not overengineered. |
| — | FK/constraint coverage | Assessed | `ON DELETE RESTRICT` default with a stated exception for append-only history tables (doc 04 §4.4) is a sound default. |
| — | Supports RT state + historical + ML + RL + simulation + recommendations + audit | Assessed | Yes, once M1/M2/M4/M5 are fixed — no missing table was found for any of these concerns. |

---

## 7. Real-time architecture findings summary

| # | Finding | Severity | Status |
|---|---|---|---|
| M5 | Idempotency undefined | Major | Fixed |
| M6 | Ordering/staleness undefined | Major | Fixed |
| — | Redis Streams topology | Assessed | Sound — consumer groups per role, replay-capable, versioned via stream-key suffixing (doc 06 §6.6). |
| — | WebSocket/dashboard updates | Assessed | Payload contract is fine; reconnect/backpressure behavior is an open minor item (§3). |

---

## 8. Simulation architecture findings summary

| # | Finding | Severity | Status |
|---|---|---|---|
| M9 | No concurrency model for parallel counterfactual runs | Major | Fixed |
| M10 | No owning process for live-demo SUMO | Major | Fixed (flagged for Phase 3) |
| — | SUMO as digital twin + RL env | Assessed | Sound design; §9.1's explicit split between the two roles is the right call and prevented a worse conflation bug. |
| — | TraCI integration boundaries | Assessed | Clean — `SumoBridge` is the single seam, action-to-TraCI-call mapping is explicit per action type. |
| — | Scenario management | Assessed | Good — parameterized, named, versioned, shared between live-demo and RL/counterfactual use. |
| — | Reproducibility | Assessed | FR-SIM-02 + seeded `SumoBridge.start()` is sufficient and consistent with doc 14's evaluation needs. |
| — | Counterfactual design | Assessed | Sound after M7's clarification that this expensive path is NOT also the training-time reward path. |

---

## 9. Scope findings

### MUST (core thesis/demo claim depends on these)
- Telemetry ingestion + fusion + live map (Phases 1-3)
- All five prediction models at the **XGBoost tier minimum** (historical-average baseline + one real ML model per target)
- Rule-based decision engine (also serves as the RL baseline and the FR-DEC-02 fallback)
- DQN agent, trained and evaluated against the rule-based and fixed-timetable baselines, on at least `normal` + one disruption scenario
- Counterfactual simulation for the recommendation flow (FR-SIM-01) on those same scenarios
- Recommendation engine with explanation + human approve/reject (FR-REC-01/02)
- Core evaluation (doc 14 §14.2, §14.3) on the MUST scenario set, with real numbers

### SHOULD (strengthens the result, do if time allows)
- LSTM tier for at least the traffic and bunching models (the two most demo-visible)
- PPO agent + DQN-vs-PPO comparison (doc 14 §14.3, secondary RQ2)
- Additional scenario coverage: `accident`, `road_closure` in the evaluation matrix
- Route rationalization (Phase 9) — valuable but not what makes the RL/prediction thesis claim
- Passenger-facing UI (already correctly marked secondary in doc 01)
- Reward-weight ablation (doc 14 §14.6, first bullet)

### ADVANCED (stretch — do not let these block MUST/SHOULD)
- LSTM tier for all five models; optional GNN for traffic
- Full stress-test matrix (doc 14 §14.4, all six traffic multipliers × all incident types)
- Prediction-informed-vs-reactive-only ablation (doc 14 §14.6, second bullet)
- Blind-top-action-vs-counterfactual ablation (doc 14 §14.6, third bullet)
- Multi-agent RL (already correctly deferred in doc 01/08)
- Full MLOps automation (drift-triggered retraining) — MLflow tracking + `model_versions` itself is MUST; the automation around it is ADVANCED

This is a staging recommendation, not a scope cut — nothing ambitious was
removed from the documents; doc 12's phase gates already support building
MUST first and layering SHOULD/ADVANCED on top without rework, because each
phase's exit criteria (doc 12) are already written at the MUST level.

### Essential gap identified (not a fix, a decision — see §12)
- **Historical training data sourcing was never addressed anywhere** before this review (doc 12 Phase 4 entry now flags it). Given the ₹0/open-data constraint, assuming a real historical transit dataset exists for an arbitrary demo city is risky. Default plan added: generate it via many extended, varied-seed SUMO runs.

### Unnecessary complexity flagged
- Attempting the LSTM/GNN tier for all five prediction models simultaneously before validating the XGBoost tier and the full pipeline end-to-end would be the single most likely way to burn the project timeline without a working demo — explicitly staged as SHOULD/ADVANCED above for this reason.

---

## 10. Cost constraint findings

- Core stack confirmed free/open-source/self-hostable end to end: OSM, SUMO,
  Postgres/PostGIS, Redis, FastAPI, Next.js, PyTorch/scikit-learn/XGBoost,
  Stable-Baselines3 (+ `sb3-contrib` for masking, still free/open-source),
  MLflow, DVC, Docker. No LLM in the critical path (per doc 01 Rule 2).
- **One real gap found and closed as a documentation fix:** map tiles for
  MapLibre (§M11) — no hidden paid dependency remains once the self-hosted
  tile plan in doc 15 §15.4a is implemented.
- **One soft cost note, not a defect:** GitHub Actions minutes are free only
  within GitHub's tier limits; irrelevant at this project's CI scale but
  worth knowing if the repo stays private and CI usage grows.
- No cloud GPU dependency — all models specified (XGBoost, small
  LSTM/GRU, DQN/PPO on a low-hundreds discrete action space) train on CPU or
  a consumer GPU in reasonable time at this project's scale.

---

## 11. Engineering quality findings

- **Naming:** consistent overall; one minor prose/code naming drift noted
  (§3, not fixed — trivial).
- **Versioning:** strong — API path versioning, event stream key
  versioning, and `model_versions` all cross-reference correctly; the one
  ambiguity found (`version` field meaning) is fixed.
- **Config/secrets handling:** sound (doc 02.5, doc 15.5) — env-var based,
  `.env.example` pattern, no plaintext secrets in the repo (confirmed by
  scan, §13 below).
- **Observability:** adequately scoped for a demo system (doc 02.8); no
  fix needed, though doc 13 doesn't yet test for trace-id propagation —
  low priority, not blocking.
- **Testing requirements:** thorough and correctly layered (doc 13);
  extended in this review to cover the new idempotency/ordering/leakage
  rules introduced by the fixes above.
- **Reproducibility:** strong — MLflow run ids, DVC, seeded simulation runs,
  and doc 14 §14.7's "no fabricated metrics" rule are all consistent with
  each other.

---

## 12. Remaining decisions requiring human approval

These are genuine design choices, not documentation bugs — this review
does not make them unilaterally:

1. **RL masking library approach (C2):** `sb3-contrib` `MaskablePPO` +
   custom-masked DQN (recommended) vs. soft penalty-based masking for both
   algorithms. Affects Phase 6 implementation directly.
2. **Historical training data source:** commit to SUMO-generated synthetic
   history as the default (recommended, doc 12 Phase 4), or invest time
   sourcing a real GTFS/GTFS-RT historical archive first.
3. **Map tile hosting tool** (doc 15 §15.4a): confirm `tileserver-gl` (or
   an equivalent self-hosted option) rather than a third-party tile API.
4. **Phone telemetry auth model:** full user JWT login per device (current
   spec) vs. a lighter per-device token scheme — a Phase 3 UX/security
   trade-off, not resolved here.
5. **MUST/SHOULD/ADVANCED staging (§9):** confirm this is the right cut for
   the project's actual deadline before Phase 4+ work begins — this review
   proposes it but the deadline/team size context to finalize it sits with
   the project owner, not the architecture review.
6. **Live-demo SUMO service** (M10): confirm it's added to doc 11's compose
   file when Phase 3 is scaffolded (flagged, not yet written since Phase 3
   hasn't started).

---

## 13. Non-architecture verification (requested alongside this review)

- Scanned the full working tree for secrets, credentials, `.env` files,
  local-machine artifacts, and AI-assistant branding/attribution strings —
  **none found**. Tree currently contains only `.git/`, `.gitignore`,
  `README.md`, and `docs/` — no stray temp files, no editor/OS artifacts.
- No AI-assistant attribution or watermark has been added to any file in
  this project, and none should be.
- **Third-party licenses/attribution:** nothing to preserve yet — no
  third-party code, OSM data extracts, or SUMO assets have been vendored
  into the repo at this stage (Phase 0 is documentation-only). This becomes
  relevant starting Phase 2 (OSM data license/attribution — ODbL requires
  attribution for published OSM-derived data) and should be revisited then,
  not before.

---

## 14. Final Phase 1 readiness assessment

**Ready for Phase 1 scaffolding: YES**, on the basis of the fixes already
applied in this review. Nothing found rises to a level that invalidates the
overall architecture or requires a redesign — every critical/major finding
was a concrete, local inconsistency (a type, a key, a missing constraint, an
unstated concurrency model, an underspecified action-space encoding), and
all have been corrected directly in the documents. The six items in §12 are
real decisions but none of them block *starting* Phase 1 (infrastructure
skeleton, doc 12) — they block Phase 3 (tile hosting, telemetry auth),
Phase 4 (data sourcing), and Phase 6 (RL masking library) specifically, and
there is runway to decide them before those phases start.

---
*Review v1.0 — Phase 0 gate. This document is itself part of the frozen
architecture set and should be updated (not deleted) if a later phase
reveals the fixes above were insufficient.*
