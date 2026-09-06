# Phase 2 Design — Transportation Domain & Spatial Data Foundation (TASK-201)

Companion to [ARCHITECTURE_REVIEW.md](ARCHITECTURE_REVIEW.md) (Phase 0) and
[PHASE1_REVIEW.md](PHASE1_REVIEW.md) (Phase 1). Records the decisions made
while reconciling TASK-201's requirements against the existing doc 01-15
architecture, since several of them extend rather than merely implement
what Phase 0 specified.

## 1. Why this document exists

TASK-201 asked for nine canonical entities (Road, RoadSegment, Intersection,
Stop, Route, RouteStop, Vehicle, VehicleAssignment, ServiceCalendar) and an
explicit principle: **PostGIS is the system of record for the road network;
an in-memory NetworkX/OSMnx graph is a derived computational view, never
the source of truth.**

Doc 04 (data model) did not previously have `roads`/`road_segments`/
`intersections` tables at all, and doc 12's Phase 2 section described the
road network as "a road graph via osmnx" — closer to "the graph is the
representation" than "the graph is derived from the database." This is a
genuine extension of Phase 0's architecture, not an implementation of
something already fully specified, and not a contradiction either — Phase 0
simply hadn't decided this yet. This document is the record of how it was
decided, so doc 04/12 can be updated precisely rather than silently.

## 2. Architecture decisions

### 2.1 PostGIS as system of record, NetworkX/OSMnx as derived

Confirmed explicitly by the task brief, not inferred. `intersections` and
`road_segments` (docs/architecture/04-data-model.md, new tables) are the
persistent, authoritative road topology. Any in-memory graph a future
routing task builds (osmnx/NetworkX) is rebuilt from these tables at
process startup or on demand — it is a cache, not a database. OSM is an
**input source**, referenced via `source`/`osm_node_id`/`osm_way_id`
columns, never the permanent domain model itself.

**Consequence for doc 12:** Phase 2's "road graph via osmnx" line is now
understood as "an osmnx graph is *built from* the persisted road network,"
not "osmnx is where the road network lives." Doc 12 is updated to say this.

### 2.2 Road vs RoadSegment vs Intersection

- **Intersection** — a vertex: an intersection, dead-end, or any point
  road topology needs a node. Every RoadSegment starts and ends at one.
- **RoadSegment** — the routable unit: one edge between two Intersections,
  with its own LineString geometry, cached length, one-way flag, and road
  class. This is what a future routing algorithm actually traverses.
- **Road** — an optional, human-meaningful grouping of RoadSegments that
  share a name (e.g. "MG Road" may be dozens of OSM ways / RoadSegments).
  `RoadSegment.road_id` is nullable — a segment doesn't need to belong to
  a named Road to exist or be routable.

This mirrors the standard road-network-vs-navigable-graph split used by
most transportation data models, and keeps `routes` (bus service paths,
already in doc 04) conceptually separate from the physical street network:
a bus Route's `geometry` is its own coarser LineString, not derived from
RoadSegments in Phase 2 — that mapping is left to later routing work.
"Route/road spatial relationships" (the spatial requirement in TASK-201) is
satisfied by both being properly-typed, GIST-indexed geometries that a
future query can relate via `ST_DWithin`/`ST_Intersects`, not by a
persisted join table added prematurely now.

### 2.3 VehicleAssignment vs the existing `trips` table

Doc 04 already has a `trips` table (`route_id`, `vehicle_id`,
`scheduled_start`, `actual_start`, `status`) — a real-time execution
concept owned by Phase 3. TASK-201 introduces `VehicleAssignment` as a
*separate*, Phase-2-scope concept, and this was ambiguous enough (two
materially different schemas depending on the answer) that it was
confirmed before implementation rather than assumed:

> **Decision:** `VehicleAssignment` is a static fleet-planning link -
> which vehicle serves which route, for which `ServiceCalendar` period
> (e.g. "BUS_07 serves Route 12 on weekdays from 2026-01-01"). It is
> independent of `trips`, which is untouched and remains Phase 3's
> real-time journey-instance tracking.

This matches GTFS's own scope boundary: static GTFS has no vehicle-to-trip
binding at all (that's a real-time/GTFS-RT concept); block-level vehicle
continuity is the closest static analog, and `VehicleAssignment` sits at
that planning level, not the individual-journey level.

### 2.4 SRID and geometry types

SRID 4326 (WGS84) throughout, matching doc 04's existing convention for
every prior geometry column (`stops.location`, `routes.geometry`,
`incidents.location`, `telemetry.location`). New columns:
`intersections.location` (`POINT`), `road_segments.geometry`
(`LINESTRING`). Distance/proximity queries cast to PostGIS `geography` at
query time (`ST_DWithin`/`ST_Distance` on a `geography` cast) rather than
storing a second geography-typed column — the standard pattern for
accurate metric distance on 4326 data without doubling storage.

### 2.5 `routes.geometry` relaxed to nullable

Doc 04's column list for `routes.geometry` didn't mark it nullable. Making
it `NOT NULL` would block creating a Route before its path is known (e.g.
before OSM ingestion / routing work in a later task computes it). Relaxed
to nullable; this is additive/safe (existing rows, if any, are unaffected;
no code assumed non-null).

### 2.6 Source tracking for idempotent ingestion (prep for a later OSM/GTFS task)

Every entity a later ingestion task will populate carries:

| Table | Idempotency key |
|---|---|
| `intersections` | `osm_node_id` (bigint, unique when present) |
| `road_segments` | `osm_way_id` (bigint, unique when present) |
| `stops` | `(source, source_id)` (unique when `source_id` present) |
| `routes` | `(source, source_id)` (unique when `source_id` present) |

All of these are plain (not partial/filtered) unique constraints on
nullable columns - Postgres already treats `NULL <> NULL`, so any number
of manually-created rows with no source id coexist freely, while a second
insert with the *same* real source id correctly conflicts. A later
ingestion task's normalization boundary is therefore: **look up by source
id first (upsert), never insert blind** - the schema enforces this rather
than merely documenting it. `roads` intentionally has no such key (it's an
aggregation Concept, not a 1:1 OSM entity mapping).

### 2.7 CHECK constraints over native Postgres ENUM

Every status/source column (`source`, `status` on the various tables) is
`text` + `CHECK (... IN (...))`, matching the convention already
established for `vehicles.status`/`source` in doc 04 - not a native
Postgres `ENUM` type. Adding an allowed value later is a constraint
migration (`ALTER TABLE ... DROP CONSTRAINT`, `ADD CONSTRAINT`), not a type
migration - cheaper and matches what Phase 0/1 already committed to.

### 2.8 No API write surface yet

`services/api` exposes GET-only endpoints for roads/segments, stops,
routes, vehicles. Doc 05 doesn't define transportation-entity write
endpoints, and the intended way these tables get populated is ingestion
(OSM in a later task, GTFS-like import per FR-INGEST-03), not a public
write API - adding one now would be exactly the "large API surface
prematurely" TASK-201 warned against. Seed/test data is created directly
through the ORM (`app/db/seed.py`, `tests/fixtures/transportation.py`),
not HTTP.

## 3. Endpoints added

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/roads` | list |
| GET | `/api/v1/roads/{road_id}` | one road + its segments |
| GET | `/api/v1/road-segments/{segment_id}` | one segment |
| GET | `/api/v1/stops` | list, paginated |
| GET | `/api/v1/stops/nearby?lat=&lon=&radius_m=` | proximity query (ST_DWithin/ST_Distance) |
| GET | `/api/v1/stops/{stop_id}` | one stop |
| GET | `/api/v1/routes` | matches doc 05 §5.3 exactly |
| GET | `/api/v1/routes/{route_id}` | one route |
| GET | `/api/v1/routes/{route_id}/stops` | matches doc 05 §5.3 + doc 12 Phase 2 exit criterion exactly |
| GET | `/api/v1/vehicles` | static registry - list, paginated |
| GET | `/api/v1/vehicles/{vehicle_id}` | one vehicle - distinct from doc 05's `/fleet` (real-time state, Phase 3) |

## 4. OSM → AURA normalization boundary (for a later ingestion task)

Not built in TASK-201 (explicitly excluded), but the schema is shaped for
it:

- An OSM **node** → an `Intersection` row, keyed by `osm_node_id`. Nodes
  that are also transit stops become a `Stop` row too (separate table,
  `source='osm'`, `source_id` = the OSM node id as text), not a reused PK -
  a `Stop` is a transit concept, an `Intersection` is a topology concept,
  and a location can be both without conflating the tables.
- An OSM **way** tagged as a road → one or more `RoadSegment` rows (split
  at intersections if the way passes through nodes shared with other
  ways), keyed by `osm_way_id`. Ways sharing a `name` tag optionally group
  under one `Road` row.
- A later task's ingestion loop should always upsert-by-source-id (§2.6),
  never blind-insert - re-running an import must be safe.
- GTFS `routes.txt`/`stops.txt`/`trips.txt`/`calendar.txt` map onto
  `Route`/`Stop`/(doc 04's existing `trips`)/`ServiceCalendar`
  respectively, each via the same `source='gtfs'` + `source_id` pattern.

## 5. Deviations from the literal doc 04 column list

| Table | Deviation | Reason |
|---|---|---|
| `routes.geometry` | now nullable | §2.5 |
| `stops`, `routes` | added `name`, `source`, `source_id` | needed for ingestion idempotency (§2.6); `stops`/`routes` previously had no human-readable name at all |
| `stops`, `routes`, `vehicles`, `route_stops` | added `created_at`/`updated_at` | doc 04 didn't specify audit timestamps on these; added for consistency with every other table doc 04 already timestamps |
| `vehicles.source`/`status` | added explicit CHECK constraints | previously freeform text with only a comment listing allowed values |

None of these change any existing behavior (Phase 1 shipped no domain
tables at all - this is the first migration to create them), so there is
nothing to migrate away from.

---
*v1.0 — Phase 2 (TASK-201).*
