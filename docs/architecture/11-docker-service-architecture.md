# 11. Docker / Service Architecture

## 11.1 `docker-compose.yml` services (dev/demo)

| Service | Image/build | Port | Depends on |
|---|---|---|---|
| `postgres` | `postgis/postgis:16-3.4` | 5432 | — |
| `redis` | `redis:7-alpine` | 6379 | — |
| `api` | build: `services/api` | 8000 | postgres, redis |
| `ingestion` | build: `services/ingestion` | 8001 | postgres, redis |
| `prediction` | build: `services/prediction` | 8002 | postgres, redis, model artifacts volume |
| `optimization` | build: `services/optimization` | 8003 | redis, rl policy artifacts volume |
| `simulation` | build: `services/simulation` | 8004 | SUMO installed in image; network/scenario files volume |
| `recommendation` | build: `services/recommendation` | 8005 | postgres, redis |
| `web` | build: `apps/web` | 3000 | api |
| `mlflow` | `ghcr.io/mlflow/mlflow` or local build | 5001 | postgres (backend store) or local file store |

All internal services communicate on a private compose network; only `api`
and `web` (and `mlflow` UI, dev-only) publish ports to the host.

## 11.2 Example skeleton

```yaml
version: "3.9"
services:
  postgres:
    image: postgis/postgis:16-3.4
    environment:
      POSTGRES_DB: aura
      POSTGRES_USER: aura
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes: [pgdata:/var/lib/postgresql/data]
    ports: ["5432:5432"]

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]

  api:
    build: ./services/api
    env_file: .env
    depends_on: [postgres, redis]
    ports: ["8000:8000"]

  ingestion:
    build: ./services/ingestion
    env_file: .env
    depends_on: [postgres, redis]

  prediction:
    build: ./services/prediction
    env_file: .env
    depends_on: [postgres, redis]
    volumes: ["./ml:/app/ml:ro"]

  optimization:
    build: ./services/optimization
    env_file: .env
    depends_on: [redis]
    volumes: ["./rl:/app/rl:ro"]

  simulation:
    build: ./services/simulation
    env_file: .env
    volumes: ["./simulation:/app/simulation:ro"]

  recommendation:
    build: ./services/recommendation
    env_file: .env
    depends_on: [postgres, redis]

  web:
    build: ./apps/web
    environment:
      NEXT_PUBLIC_API_URL: http://localhost:8000
    depends_on: [api]
    ports: ["3000:3000"]

  mlflow:
    image: ghcr.io/mlflow/mlflow:latest
    command: mlflow server --host 0.0.0.0 --backend-store-uri sqlite:///mlflow.db
    ports: ["5001:5000"]
    volumes: [mlflowdata:/mlflow]

volumes:
  pgdata:
  mlflowdata:
```

This is illustrative for Phase 1 scaffolding, not final — exact env vars,
healthchecks, and volume mounts get filled in when each service is built.

## 11.3 Environments

| Env | Purpose | Notes |
|---|---|---|
| `local` | developer machine, `docker-compose up` | default `.env`, seed data |
| `demo` | SIH/thesis demonstration | same compose stack, possibly on a single beefier machine for SUMO performance |
| `ci` | GitHub Actions | services built and tested in isolation + a docker-compose-based integration test job (doc 13) |

No separate "production" environment is in scope for v1 (doc 02.3, doc 15) —
this is a research/demo system, and that should be stated plainly rather than
implying a production deployment exists.

## 11.4 CI/CD (GitHub Actions)

- `ci.yml`: on PR — lint (ruff/eslint), unit tests per service/ml/rl, type
  checks (mypy/tsc).
- `integration.yml`: on PR to main — `docker-compose -f docker-compose.ci.yml up`,
  run `tests/` integration suite against the live stack, tear down.
- `ml-eval.yml` (manual/scheduled): runs the doc 14 evaluation harness and
  publishes metrics as a PR comment/artifact when a model or RL agent changes.

---
*v1.0 — Phase 0.*
