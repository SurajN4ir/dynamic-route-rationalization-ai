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

## Change control

This is "frozen" in the sense that Phase 1+ work should not silently drift
from it. It is not immutable — amend it deliberately, with a reason, not by
accretion during unrelated feature work.
