"""Current vehicle state - see docs/architecture/TASK204_DESIGN.md §8/§9/§10.

Redis holds the latest state as a fast-path cache (`aura:vehicle_state:
{vehicle_id}`, TTL-bounded so a vehicle that stops transmitting forever
doesn't grow the keyspace unboundedly - TASK-204 §25). Postgres's
`telemetry` table is the durable source of truth `get_vehicle_state`
falls back to on a cache miss or a Redis outage (TASK-204 §11/§26) - the
cache is a read optimization over data that's always independently
reconstructable, never the only copy.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

import redis.asyncio as redis
from geoalchemy2.shape import to_shape
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.telemetry import Telemetry
from app.repositories.telemetry import get_active_assignment, get_latest_telemetry
from app.schemas.telemetry import VehicleAssignmentSummary, VehicleStateRead
from app.telemetry.freshness import classify_freshness

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CurrentVehicleState:
    vehicle_id: uuid.UUID
    latitude: float
    longitude: float
    speed_mps: float
    heading_deg: float | None
    ts: datetime
    road_segment_id: uuid.UUID | None
    segment_distance_m: float | None


def _cache_key(vehicle_id: uuid.UUID) -> str:
    return f"aura:vehicle_state:{vehicle_id}"


def _to_json(state: CurrentVehicleState) -> str:
    payload = asdict(state)
    payload["vehicle_id"] = str(state.vehicle_id)
    payload["road_segment_id"] = str(state.road_segment_id) if state.road_segment_id else None
    payload["ts"] = state.ts.isoformat()
    return json.dumps(payload)


def _from_json(raw: str) -> CurrentVehicleState:
    payload = json.loads(raw)
    return CurrentVehicleState(
        vehicle_id=uuid.UUID(payload["vehicle_id"]),
        latitude=payload["latitude"],
        longitude=payload["longitude"],
        speed_mps=payload["speed_mps"],
        heading_deg=payload["heading_deg"],
        ts=datetime.fromisoformat(payload["ts"]),
        road_segment_id=uuid.UUID(payload["road_segment_id"])
        if payload["road_segment_id"]
        else None,
        segment_distance_m=payload["segment_distance_m"],
    )


async def write_cached_state(
    redis_client: redis.Redis, state: CurrentVehicleState, *, ttl_s: int
) -> None:
    await redis_client.set(_cache_key(state.vehicle_id), _to_json(state), ex=ttl_s)


async def read_cached_state(
    redis_client: redis.Redis, vehicle_id: uuid.UUID
) -> CurrentVehicleState | None:
    raw = await redis_client.get(_cache_key(vehicle_id))
    if raw is None:
        return None
    return _from_json(raw)


def _state_from_telemetry_row(row: Telemetry) -> CurrentVehicleState:
    point = to_shape(row.location)
    return CurrentVehicleState(
        vehicle_id=row.vehicle_id,
        latitude=point.y,
        longitude=point.x,
        speed_mps=row.speed_mps,
        heading_deg=row.heading_deg,
        ts=row.ts,
        road_segment_id=row.road_segment_id,
        segment_distance_m=row.segment_distance_m,
    )


async def get_vehicle_state(
    session: AsyncSession,
    redis_client: redis.Redis | None,
    vehicle_id: uuid.UUID,
    *,
    now: datetime,
    stale_threshold_s: int,
    offline_threshold_s: int,
) -> VehicleStateRead | None:
    """Redis-first, Postgres-fallback current-state lookup. Returns
    `None` only when the vehicle has never reported any telemetry at all
    - distinct from "offline" (TASK-204 §9), which still returns a state,
    just a stale one."""
    state: CurrentVehicleState | None = None

    if redis_client is not None:
        try:
            state = await read_cached_state(redis_client, vehicle_id)
        except Exception:
            logger.warning("redis unavailable for state read; falling back to Postgres")

    if state is None:
        row = await get_latest_telemetry(session, vehicle_id)
        if row is None:
            return None
        state = _state_from_telemetry_row(row)

    age_s = (now - state.ts).total_seconds()
    freshness = classify_freshness(
        age_s, stale_threshold_s=stale_threshold_s, offline_threshold_s=offline_threshold_s
    )

    assignment_row = await get_active_assignment(session, vehicle_id, now.date())
    assignment = (
        VehicleAssignmentSummary(
            route_id=assignment_row.route_id, service_calendar_id=assignment_row.service_calendar_id
        )
        if assignment_row is not None
        else None
    )

    return VehicleStateRead(
        vehicle_id=state.vehicle_id,
        latitude=state.latitude,
        longitude=state.longitude,
        speed_mps=state.speed_mps,
        heading_deg=state.heading_deg,
        ts=state.ts if state.ts.tzinfo else state.ts.replace(tzinfo=UTC),
        road_segment_id=state.road_segment_id,
        segment_distance_m=state.segment_distance_m,
        freshness=freshness,
        active_assignment=assignment,
    )
