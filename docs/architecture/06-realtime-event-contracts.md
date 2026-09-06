# 6. Real-Time Event Contracts

Redis Streams is the backbone for everything that happens "live." Every
producer/consumer speaks the schemas below — this is what makes phone
telemetry and SUMO telemetry interchangeable (Rule: "same telemetry
contract" in the architecture overview).

## 6.1 Canonical telemetry contract

**TASK-204 implemented shape** (see
[TASK204_DESIGN.md](TASK204_DESIGN.md) §1/§2 — the fields below are what
`POST /api/v1/telemetry` actually accepts today):

```json
{
  "vehicle_id": "uuid",
  "timestamp": "2026-09-06T10:15:30Z",
  "latitude": 12.9716,
  "longitude": 77.5946,
  "speed_mps": 8.3,
  "heading_deg": 142.0,
  "accuracy_m": 5.0,
  "source": "phone | sumo | synthetic"
}
```

`route_id`/`trip_id`/`occupancy` from this contract's original v1.0 draft
were **dropped**, not deferred: `trips` was never built (TASK-201 built
`vehicle_assignments` instead, kept independent of raw position
telemetry), and embedding an assignment reference on every raw GPS ping
would conflate "where is the vehicle" with "what is it assigned to" —
assignment is resolved separately, on read, from `VehicleAssignment`
(TASK204_DESIGN.md §13). `occupancy` has no consumer yet (a future
demand-prediction concern). `accuracy_m` (optional) was added — it has an
immediate consumer (segment-association confidence) that didn't exist
when this contract was first drafted. `source` gained a `synthetic` value
for the test/dev producer TASK-204's brief explicitly asked for.

Validation rules (enforced by `app/telemetry/validation.py` +
`TelemetryIngestRequest`'s Pydantic field constraints — TASK-204 built
this inside `services/api`, not a separate `services/ingestion` process;
see TASK204_DESIGN.md §2 placement note):
- `latitude`/`longitude` in valid range (`[-90,90]`/`[-180,180]`). A
  configured service-area bounding box is **not yet enforced** — no
  specific demo service area has been chosen anywhere in this project yet
  (TASK204_DESIGN.md §17).
- `speed_mps` in `[0, 40]` (~144 km/h ceiling; anything above is rejected as sensor error, not clamped).
- `timestamp` within `[-30s, +5s]` of server receipt time (clock skew tolerance).
- `vehicle_id` must reference a known `vehicles` row.

### 6.1a Idempotency

A client (phone or SUMO bridge) may retry a POST after a timeout without
knowing whether the first attempt succeeded. Ingestion writes telemetry with
`INSERT ... ON CONFLICT (vehicle_id, ts, source) DO NOTHING` against the
unique constraint in doc 04 §4.2 (`telemetry`) — a retried identical sample
is a safe no-op, not a duplicate row. Clients should retry with the *same*
`timestamp` they originally sampled at, not a new one, for this to work.

### 6.1b Ordering & stale data

Telemetry can arrive out of order (network jitter means an older sample can
arrive after a newer one). Two different concerns, handled differently:

- **History** (`telemetry` table): every valid, non-duplicate sample is
  appended regardless of arrival order — it's the record of what happened.
- **Current state** (the Redis-backed fused cache that `/fleet` and the
  live map read): the fusion worker only overwrites a vehicle's cached
  state if the incoming sample's `timestamp` is newer than the cached
  state's timestamp. An out-of-order (late-arriving, older) sample updates
  history but never regresses the live view.
- **Staleness:** if no valid sample for a vehicle has updated its cached
  state for more than `STALE_THRESHOLD_S` (default **15s** — three missed
  samples at the 1-per-5s cadence, doc 01 INGEST-01), the fusion worker
  emits a `telemetry_anomaly` event (`anomaly_type: "stale"`, §6.5) and the
  API marks that vehicle `stale` in `/fleet` rather than silently freezing
  its marker at the last known position (closes FR-EVENT-03, which
  previously left the dropout threshold undefined).

## 6.2 Redis Streams topics

**Not yet implemented.** TASK-204 deliberately does not stand up Redis
Streams or consumer groups — `app/cache/redis.py` explicitly reserves
itself as their future home but says not to build them yet, and no
fusion-worker/prediction/WS-fan-out service exists to consume them.
TASK-204 instead uses a single Redis cache key per vehicle
(`aura:vehicle_state:{vehicle_id}`) behind one internal publication
function (`app/telemetry/publisher.py:publish_state_update`) — the seam
a future task attaches the topics below to, without changing the
ingestion pipeline itself (TASK204_DESIGN.md §10/§12/§18). The table
below remains the target design for when that future task lands.

| Stream key | Producer | Consumer(s) | Payload |
|---|---|---|---|
| `stream:telemetry:raw` | ingestion | fusion worker | canonical telemetry (6.1) |
| `stream:telemetry:fused` | fusion worker | state cache writer, prediction engine, WS fan-out | telemetry + `matched_edge_id`, `headway_s`, `delay_s` |
| `stream:events:bunching` | prediction (bunching model) | event engine, decision engine, WS fan-out | see 6.3 |
| `stream:events:incident` | ingestion | event engine, decision engine, WS fan-out | see 6.4 |
| `stream:events:anomaly` | fusion worker | event engine, WS fan-out | see 6.5 |
| `stream:recommendations` | recommendation engine | WS fan-out, audit logger | `Recommendation` (doc 04) |

Consumer groups are used per consumer role (e.g. `cg:prediction`,
`cg:ws-fanout`) so each stream can be read independently and replayed for
debugging without re-ingesting telemetry.

## 6.3 Bunching event

```json
{
  "event_type": "bunching_risk",
  "route_id": "uuid",
  "leading_vehicle_id": "uuid",
  "trailing_vehicle_id": "uuid",
  "probability": 0.86,
  "expected_time_to_bunch_s": 480,
  "model_version_id": "uuid",
  "generated_at": "2026-09-06T10:15:32Z"
}
```

## 6.4 Incident event

```json
{
  "event_type": "incident_impact",
  "incident_id": "uuid",
  "affected_route_ids": ["uuid"],
  "affected_edge_ids": ["osm_edge_id"],
  "severity": "high",
  "detected_at": "2026-09-06T10:16:00Z"
}
```

## 6.5 Anomaly event

```json
{
  "event_type": "telemetry_anomaly",
  "vehicle_id": "uuid",
  "anomaly_type": "dropout | teleport | stale",
  "last_seen_at": "2026-09-06T10:10:00Z",
  "detected_at": "2026-09-06T10:16:05Z"
}
```

## 6.6 Versioning & compatibility

- Every event payload carries `event_type` and, where applicable,
  `model_version_id` — consumers must ignore unknown fields (additive
  evolution only) and switch on `event_type`/schema version rather than
  payload shape.
- A breaking payload change requires a new stream key suffix (e.g.
  `stream:events:bunching:v2`) run in parallel until consumers migrate —
  mirrors the API versioning policy in doc 05.

---
*v1.1 — Phase 0 baseline, §6.1 corrected to TASK-204's actual implemented
contract and §6.2 annotated as not yet implemented. See
[TASK204_DESIGN.md](TASK204_DESIGN.md) for the reasoning.*
