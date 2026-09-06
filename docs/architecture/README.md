# AURA Architecture v1.0 (frozen — Phase 0)

This directory is the single source of truth for AURA's architecture. Nothing
in `apps/`, `services/`, `ml/`, or `rl/` should contradict it; if implementation
reveals that a document here is wrong, update the document in the same PR that
changes the code, and bump the version note at the bottom of the affected file.

## Reading order

1. [Functional requirements](01-functional-requirements.md)
2. [Non-functional requirements](02-non-functional-requirements.md)
3. [Component architecture](03-component-architecture.md)
4. [Data model (ER)](04-data-model.md)
5. [API specification](05-api-specification.md)
6. [Real-time event contracts](06-realtime-event-contracts.md)
7. [ML model contracts](07-ml-model-contracts.md)
8. [RL state/action/reward specification](08-rl-specification.md)
9. [SUMO integration architecture](09-sumo-integration.md)
10. [Repository structure](10-repository-structure.md)
11. [Docker / service architecture](11-docker-service-architecture.md)
12. [Development phases & acceptance criteria](12-development-phases.md)
13. [Testing strategy](13-testing-strategy.md)
14. [Evaluation methodology](14-evaluation-methodology.md)
15. [Deployment architecture](15-deployment-architecture.md)

**Gate reviews:**
- [ARCHITECTURE_REVIEW.md](ARCHITECTURE_REVIEW.md) — Phase 0 review verdict
  (APPROVED WITH CHANGES), all findings, and every fix already applied to
  docs 04/06/07/08/09/12/13/15 as a result.
- [PHASE1_REVIEW.md](PHASE1_REVIEW.md) — Phase 1 implementation review
  (APPROVED WITH FIXES APPLIED): a real cross-event-loop connection pool
  bug in the test suite and a Docker build-arg misconfiguration for the
  frontend, both fixed and re-verified.
- [PHASE2_DESIGN.md](PHASE2_DESIGN.md) — Phase 2 / TASK-201 design record:
  the transportation domain + spatial schema decisions (Road/RoadSegment/
  Intersection as a persisted PostGIS system of record, VehicleAssignment
  vs. `trips`, SRID/idempotency conventions) and every additive change
  applied to doc 04/12 as a result.
- [TASK202_DESIGN.md](TASK202_DESIGN.md) — TASK-202 (OSM road-network
  ingestion) design record: the OSM→AURA mapping, supported tag policy,
  directionality/topology rules, idempotency/transaction/dry-run strategy,
  and a schema-correction migration (`0003`) fixing a gap PHASE2_DESIGN.md
  had specified but TASK-201's committed migration hadn't actually
  implemented (way-splitting needs a composite, not single-column, unique
  key on `road_segments`).
- [TASK203_DESIGN.md](TASK203_DESIGN.md) — TASK-203 (canonical road graph
  construction) design record: `Intersection`/`RoadSegment` → NetworkX
  `MultiDiGraph` node/edge mapping, the multi-edge and self-loop decisions,
  the reference-only geometry strategy, why NetworkX was chosen over
  OSMnx, and a doc 12 correction (TASK-203 is graph construction only —
  routing algorithms were split out to a future task, not built here).
- [TASK204_DESIGN.md](TASK204_DESIGN.md) — TASK-204 (real-time vehicle
  telemetry & network state) design record: the telemetry event model,
  idempotency/ordering/stale-state policies, nearest-segment association
  (explicitly not map matching), the Redis-cache/Postgres-durable current
  state split, and doc 04/06 corrections (the `telemetry` table's actual
  shape vs. its Phase-0 draft, and why `route_id`/`trip_id`/`occupancy`
  were dropped from the wire contract).
- [TASK205_DESIGN.md](TASK205_DESIGN.md) — TASK-205 (prediction data &
  feature foundation) design record: the feature contract, the
  `road_segment x timestamp` traffic grain's static/temporal/telemetry-
  derived features, the strict leakage boundary (`ts < T`), why
  ETA/Delay/Demand/Bunching targets are defined but their generation is
  deferred (each cites its specific missing data dependency), and the
  `ml/common/` placement decision (no dedicated feature-store product,
  no new Postgres table — CSV + manifest under `data/features/`).

## Change control

This is "frozen" in the sense that Phase 1+ work should not silently drift
from it. It is not immutable — amend it deliberately, with a reason, not by
accretion during unrelated feature work.
