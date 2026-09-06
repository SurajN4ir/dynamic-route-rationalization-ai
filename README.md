# AURA — Adaptive Urban Route & Fleet Intelligence

**Formal title:** AI/ML-Powered Dynamic Public Transport Route Rationalization and Fleet Optimization Using Real-Time Data and Reinforcement Learning

AURA is a decision-support system for public bus networks. It ingests live and
historical telemetry, predicts near-term network state (traffic, ETAs, delay,
demand, bunching), uses reinforcement learning to propose fleet interventions,
validates each candidate action in a SUMO digital twin, and presents an
explainable, human-approved recommendation to a transport controller.

This repository is currently in **Phase 0 — Architecture**. No application
code has been written yet; see [`docs/architecture/`](docs/architecture/README.md)
for the frozen v1.0 architecture that all later phases implement against.

## Status

| Phase | Name | Status |
|---|---|---|
| 0 | Architecture | ✅ done ([review](docs/architecture/ARCHITECTURE_REVIEW.md), commit `b9ae090`) |
| 1 | Infrastructure skeleton | 🟡 in progress |
| 2 | Transportation foundation | ⬜ not started |
| 3 | Real-time engine | ⬜ not started |
| 4 | Prediction | ⬜ not started |
| 5 | Decision engine | ⬜ not started |
| 6 | Reinforcement learning | ⬜ not started |
| 7 | Digital twin | ⬜ not started |
| 8 | Recommendation system | ⬜ not started |
| 9 | Route rationalization | ⬜ not started |
| 10 | MLOps | ⬜ not started |
| 11 | Final evaluation | ⬜ not started |

See [`docs/architecture/12-development-phases.md`](docs/architecture/12-development-phases.md)
for entry/exit criteria on each phase.

## Principles

1. Prediction (ML), decision (RL/optimization), routing (graph algorithms) and
   validation (simulation) are separate concerns — never collapsed into one model.
2. No LLM in the operational path.
3. ₹0 stack — open data, open-source tooling only.
4. No operational action ships without being tested in the SUMO digital twin first.
5. Every model/agent has a baseline, an evaluation dataset, and measured metrics.
6. Humans approve or reject every recommendation; nothing is fully autonomous.

## Repository layout

See [`docs/architecture/10-repository-structure.md`](docs/architecture/10-repository-structure.md).
Directories for phases not yet built contain only a placeholder `README.md`
explaining what will live there and when.

## Getting started (Phase 1 foundation)

Requires Docker Desktop, or Python 3.11 + [uv](https://docs.astral.sh/uv/)
and Node.js 22 for running services outside containers.

```bash
cp .env.example .env
docker compose up --build
docker compose exec api alembic upgrade head   # first run only
```

- API: http://localhost:8000 (`/healthz`, `/readyz`, `/api/v1/status`, `/docs`)
- Web: http://localhost:3000

Running the backend without Docker:

```bash
uv sync --extra dev
uv run uvicorn app.main:app --reload --app-dir services/api
uv run pytest
```

Running the frontend without Docker:

```bash
cd apps/web
npm install
npm run dev
```
