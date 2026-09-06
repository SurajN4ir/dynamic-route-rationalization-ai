# 10. Repository Structure

Monorepo. Every top-level directory maps to a concept in doc 03
(component architecture) — no directory should be added without a
corresponding entry here.

```
aura/
├── apps/
│   ├── web/                 # Next.js + TypeScript: controller + passenger dashboards
│   └── telemetry/           # Browser-based phone GPS client; SUMO telemetry bridge adapter
│
├── services/
│   ├── api/                 # FastAPI gateway: auth, REST, WebSocket fan-out (doc 05)
│   ├── ingestion/           # Telemetry/static/incident ingestion + validation (doc 06)
│   ├── prediction/          # Serves traffic/ETA/delay/demand/bunching models (doc 07)
│   ├── optimization/        # Rule engine, constraint validator, RL agent inference (doc 08)
│   ├── simulation/          # SUMO/TraCI orchestration, scenario runner (doc 09)
│   └── recommendation/      # Ranking, explanation, controller decision + audit log
│
├── ml/
│   ├── common/              # TASK-205: shared feature contract, static/temporal/
│   │                        # telemetry-derived feature computation, target
│   │                        # definitions, dataset generation - not one model's
│   │                        # code, imported by every ml/<model>/features.py below
│   │                        # (doc 07 §7.7's "avoid duplicated feature logic")
│   ├── traffic/             # features.py, train.py, models/, evaluation notebooks
│   ├── eta/
│   ├── delay/
│   ├── demand/
│   └── bunching/
│       # each: features.py | train.py | predict.py | tests/ | README with current model + metrics
│
├── rl/
│   ├── environments/        # aura_env.py (Gymnasium wrapper over SumoBridge)
│   ├── agents/               # dqn.py, ppo.py, rule_based.py, fixed_timetable.py
│   ├── rewards/              # weights.yaml + reward.py
│   ├── policies/             # trained policy artifacts (tracked via DVC, not committed raw)
│   └── evaluation/           # shared harness running all agents through the same scenarios (doc 14)
│
├── simulation/
│   ├── networks/             # SUMO .net.xml per city/service area, generated not hand-edited
│   ├── routes/                # bus route + stop definitions (.rou.xml, additional files)
│   ├── scenarios/             # scenario configs (doc 09 §9.3), versioned YAML/JSON
│   └── sumo/                  # build_network.py, telemetry bridge script, TraCI helpers
│
├── data/
│   ├── raw/                   # DVC-tracked, never committed to git directly
│   ├── processed/
│   └── features/
│
├── infrastructure/
│   ├── postgres/               # init SQL / migrations (or a migrations/ dir at repo root, see below)
│   ├── redis/
│   ├── docker/                 # per-service Dockerfiles if not colocated
│   └── monitoring/             # logging config, minimal metrics setup
│
├── experiments/                 # MLflow-tracked experiment configs/scripts (doc 14)
│
├── tests/                        # cross-service integration tests (doc 13); unit tests live next to their code
│
├── docs/
│   └── architecture/             # this directory
│
├── docker-compose.yml
├── pyproject.toml                 # shared Python tooling config (services/, ml/, rl/)
└── README.md
```

## Conventions

- Python services/ML/RL share one `pyproject.toml` at the root (single
  virtualenv for local dev) unless a dependency conflict forces a split —
  don't pre-split into per-service Poetry projects speculatively.
- `apps/web` is a standard Next.js app with its own `package.json`.
- Database schema (doc 04) lives as versioned migrations — a `migrations/`
  directory (Alembic) at repo root, referenced by `services/api` and any
  service that owns tables (doc 03.2), not duplicated per service.
- Every `ml/<model>/` and `rl/agents/<algo>.py` module must have a README
  stating: current best model/version, metrics vs. baseline, and how to
  reproduce training — this is what doc 14's evaluation report is built from,
  not a separate document maintained by hand.
- Large binary artifacts (trained models, SUMO network files beyond a small
  demo network, raw datasets) go through DVC, not raw git.

---
*v1.1 — Phase 0 baseline, `ml/common/` (TASK-205's shared feature
foundation) added in place. See [TASK205_DESIGN.md](TASK205_DESIGN.md)
for the reasoning.*
