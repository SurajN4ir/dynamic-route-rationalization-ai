# 15. Deployment Architecture

## 15.1 Scope

AURA v1 is a research/demo system (see doc 02.3, doc 11.3) — this document
describes how to stand it up for development and for a live demonstration
(SIH judging, thesis defense), not a hardened production rollout for a real
transit agency. State that distinction explicitly wherever this doc is
referenced externally.

## 15.2 Local development

`docker-compose up` (doc 11) on a single developer machine. Requirements:
Docker Desktop, ~8GB RAM free (SUMO + Postgres + Redis + multiple Python
services + Next.js), SUMO installed in the `simulation`/`optimization`
service images (not on the host directly, so the dev machine's own SUMO
version doesn't drift from what's tested in CI).

## 15.3 Demo deployment

Two acceptable options, in order of preference:

1. **Single machine, same Docker Compose stack**, run on a laptop/desktop
   with enough CPU for SUMO to keep up with the live-demo real-time factor
   (doc 09 §9.7) plus the ML/RL inference services. This is the default —
   it's ₹0, and it's exactly what's been tested.
2. **Free-tier cloud VM** (if a live/remote demo is needed, e.g. judges
   accessing it themselves) — a single VM running the same Compose stack.
   Must remain within free-tier limits to honor the ₹0 architecture
   principle (doc 01 Rule 3); if it can't, prefer option 1.

No Kubernetes, no managed database service, no CDN — unnecessary complexity
for a demo-scale, single-instance system.

## 15.4 Data for the demo

- A bounded real-world service area (OSM extract) with real route/stop
  data if obtainable (e.g. from a public GTFS feed for the chosen city), or
  a realistic synthetic network if not — either is acceptable, but the
  final report must state which was used and why (data honesty, doc 02.4).
- 1-3 real phones providing live telemetry (FR-INGEST-01) plus a
  SUMO-simulated fleet (doc 09 §9.6) filling out the rest of the network,
  per the original demo design (Section 32 of the project brief: "phones →
  real buses, SUMO → 50+ simulated buses").

## 15.4a Map tiles (open item — see architecture review)

`apps/web` renders MapLibre, which needs a tile source; nothing in this
document set has selected one yet, which is a silent gap against the ₹0
principle (doc 01 Rule 3) if it defaults to a third-party hosted tile
service with its own usage limits/pricing. **Default plan:** self-host
tiles generated from the same OSM extract already used for the road graph
(doc 09 §9.2) via a local vector-tile server (e.g. `tileserver-gl` against
an `mbtiles` file built from the extract), run as another `docker-compose`
service — no external tile host in the critical path. Pick and document the
specific tool before Phase 3 (live map) needs it.

## 15.5 Secrets & configuration

- `.env` file per environment (`local`, `demo`, `ci`), never committed;
  `.env.example` committed with placeholder values documenting required
  vars (DB credentials, JWT secret, service URLs).
- No paid API keys required anywhere (Rule 3) — nothing to rotate or protect
  beyond DB credentials and the JWT signing secret.

## 15.6 Backups / data retention

- For a demo system, a daily `pg_dump` of the Postgres volume is sufficient;
  no requirement for point-in-time recovery or multi-region redundancy.
- Telemetry history can grow quickly at demo scale over multiple days of
  running — document a simple retention policy (e.g. keep raw telemetry for
  30 days, keep aggregated `traffic_observations`/`demand_observations`
  indefinitely) rather than letting the table grow unbounded, per NFR
  scalability targets (doc 02.2).

## 15.7 Rollback

Given the single-instance, non-production nature of this deployment,
rollback is: redeploy the previous Docker image tags via `docker-compose
up` after a `git checkout` of the previous release tag — no blue/green or
canary infrastructure is warranted at this scale.

---
*v1.0 — Phase 0.*
