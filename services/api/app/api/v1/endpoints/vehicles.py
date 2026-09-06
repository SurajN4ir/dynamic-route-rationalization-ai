"""Static vehicle registry - distinct from doc 05's `/fleet` (real-time
vehicle state, Phase 3). This is "what vehicles exist", not "where are
they right now"."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.repositories import vehicles as vehicles_repo
from app.schemas.vehicle import VehicleRead

router = APIRouter(prefix="/vehicles", tags=["vehicles"])


@router.get("", response_model=list[VehicleRead])
async def list_vehicles(
    session: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[VehicleRead]:
    vehicles = await vehicles_repo.list_vehicles(session, limit=limit, offset=offset)
    return [VehicleRead.model_validate(v) for v in vehicles]


@router.get("/{vehicle_id}", response_model=VehicleRead)
async def get_vehicle(
    vehicle_id: uuid.UUID, session: Annotated[AsyncSession, Depends(get_db)]
) -> VehicleRead:
    vehicle = await vehicles_repo.get_vehicle(session, vehicle_id)
    if vehicle is None:
        raise NotFoundError(f"Vehicle {vehicle_id} not found.")
    return VehicleRead.model_validate(vehicle)
