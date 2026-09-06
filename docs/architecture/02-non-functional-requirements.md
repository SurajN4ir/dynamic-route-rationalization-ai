# 2. Non-Functional Requirements

## 2.1 Performance

| Metric | Target | Notes |
|---|---|---|
| Telemetry ingest → visible on live map | < 5s p95 | ingestion → Redis → WebSocket push |
| Telemetry ingest API latency | < 500ms p99 at 200 concurrent vehicles | see FR-INGEST-01 |
| ETA/delay/bunching prediction serving latency | < 300ms p99 per request | inference only, model already loaded |
| RL action query latency | < 1s p99 | single-agent inference, demo-scale state |
| Counterfactual simulation (4 candidate actions, 10 min horizon) | < 30s wall clock | acceptable for human-in-the-loop review, not real-time control |
| Dashboard initial load | < 3s on broadband | Next.js SSR/static where possible |

These are demo/thesis-scale targets, not production SLAs for a city-wide deployment — call that out explicitly in the final report rather than overclaiming.

## 2.2 Scalability

- Designed scale for the SIH demo / thesis evaluation: **1 network, ≤ 500 stops, ≤ 100 concurrent vehicles (real + simulated combined)**.
- Architecture must not preclude horizontal scaling later (stateless API/services behind a load balancer, Redis Streams as a natural consumer-group boundary) but v1 does not need to prove it at city scale.

## 2.3 Reliability & availability

- No component is a single point of failure for *observation*: if the RL/decision service is down, the system degrades to the rule-based controller (FR-DEC-02) and the live map/telemetry path keeps working.
- Simulation engine failures must not block the live dashboard — a failed SUMO run surfaces as a visible error on the specific recommendation, not a system-wide outage.
- Target uptime for the demo deployment: best-effort (not a production SLA). Document this explicitly rather than inventing a number.

## 2.4 Data quality & integrity

- All telemetry validated at ingestion (FR-INGEST-06) — invalid data never reaches the state engine.
- Every prediction and recommendation is traceable to the model version and input snapshot that produced it (auditability, not just correctness).
- Simulation results are reproducible given (scenario, action, seed) — required for evaluation credibility (doc 14).

## 2.5 Security & privacy

- Phone telemetry client sends only vehicle-level GPS/speed/heading — no passenger PII collected in v1.
- API authentication: JWT-based auth for controller dashboard and telemetry clients; no unauthenticated write endpoints.
- Secrets (DB credentials, JWT signing key) via environment variables / `.env`, never committed. `.gitignore` covers `.env*`.
- No paid third-party API calls, so no external data egress of location data beyond the system's own database (see Rule 3, ₹0 architecture).

## 2.6 Cost

- ₹0 running cost by construction: OSM (free), SUMO (open-source), self-hosted Postgres/Redis, local model training. No paid maps, routing, or LLM APIs anywhere in the critical path.
- If a cloud deployment is used for the demo (doc 15), prefer free-tier / self-hosted options; any cost incurred must be explicit and approved, not incidental.

## 2.7 Maintainability

- Monorepo with clear service boundaries (doc 10); each service independently runnable via Docker Compose (doc 11).
- Every ML/RL component has: documented input/output contract (doc 07/08), a baseline, a tracked experiment (MLflow), and a versioned artifact (DVC/model registry) — no undocumented pickle files.
- Architecture docs (this directory) are the source of truth; code review should reject drift without a corresponding doc update.

## 2.8 Observability

- Structured logging (JSON) from all services, correlated by a request/trace id.
- Model predictions and RL decisions are logged with enough context (state snapshot, model version, output) to reconstruct "why" after the fact — required for the explainability requirement (FR-REC-01) and for debugging.
- Basic metrics (request latency, error rate, queue depth) exposed per service; a lightweight dashboard (even just MLflow + logs for v1) is acceptable — no requirement to stand up a full Prometheus/Grafana stack unless time permits.

## 2.9 Explainability

- Every AI-originated recommendation must carry a human-readable cause and expected-impact explanation (FR-REC-01) — "because X, we recommend Y, expected effect Z" — not a bare action label. This is a hard requirement, not a nice-to-have, because the system is human-in-the-loop by design (Rule 4, doc 01 FR-REC-02).

## 2.10 Portability

- Runs on a single developer machine via Docker Compose (Windows/Linux/Mac) for development and demo. No dependency on a specific cloud provider.

---
*v1.0 — Phase 0.*
