"""Real-time fleet state - doc 05 §5.3's `/fleet`/`/fleet/{vehicle_id}`
(current position, speed, delay, status, anomaly flags), backed by
TASK-204's telemetry pipeline. Distinct from `/vehicles` (TASK-201's
static registry - "what vehicles exist", not "where are they now")."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

import redis.asyncio as redis
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.redis import get_redis
from app.core.config import get_settings
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.repositories.telemetry import list_vehicle_ids_with_telemetry
from app.schemas.telemetry import VehicleStateRead
from app.telemetry.state import get_vehicle_state

router = APIRouter(prefix="/fleet", tags=["fleet"])


@router.get("", response_model=list[VehicleStateRead])
async def list_fleet_state(
    session: Annotated[AsyncSession, Depends(get_db)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
) -> list[VehicleStateRead]:
    settings = get_settings()
    now = datetime.now(UTC)
    vehicle_ids = await list_vehicle_ids_with_telemetry(session)

    states = []
    for vehicle_id in vehicle_ids:
        state = await get_vehicle_state(
            session,
            redis_client,
            vehicle_id,
            now=now,
            stale_threshold_s=settings.telemetry_stale_threshold_s,
            offline_threshold_s=settings.telemetry_offline_threshold_s,
        )
        if state is not None:
            states.append(state)
    return states


@router.get("/{vehicle_id}", response_model=VehicleStateRead)
async def get_fleet_state(
    vehicle_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
) -> VehicleStateRead:
    settings = get_settings()
    state = await get_vehicle_state(
        session,
        redis_client,
        vehicle_id,
        now=datetime.now(UTC),
        stale_threshold_s=settings.telemetry_stale_threshold_s,
        offline_threshold_s=settings.telemetry_offline_threshold_s,
    )
    if state is None:
        raise NotFoundError(f"No telemetry recorded for vehicle {vehicle_id}.")
    return state
