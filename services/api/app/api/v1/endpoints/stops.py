from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.repositories import stops as stops_repo
from app.schemas.stop import StopRead, stop_to_read

router = APIRouter(prefix="/stops", tags=["stops"])


@router.get("", response_model=list[StopRead])
async def list_stops(
    session: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[StopRead]:
    stops = await stops_repo.list_stops(session, limit=limit, offset=offset)
    return [stop_to_read(s) for s in stops]


@router.get("/nearby", response_model=list[StopRead])
async def find_stops_nearby(
    session: Annotated[AsyncSession, Depends(get_db)],
    lat: Annotated[float, Query(ge=-90, le=90)],
    lon: Annotated[float, Query(ge=-180, le=180)],
    radius_m: Annotated[float, Query(gt=0, le=50_000)] = 500,
) -> list[StopRead]:
    """Proximity query demonstrating PostGIS ST_DWithin/ST_Distance usage
    (docs/architecture/PHASE2_DESIGN.md spatial requirements)."""
    stops = await stops_repo.find_stops_near(session, lon=lon, lat=lat, radius_m=radius_m)
    return [stop_to_read(s) for s in stops]


@router.get("/{stop_id}", response_model=StopRead)
async def get_stop(
    stop_id: uuid.UUID, session: Annotated[AsyncSession, Depends(get_db)]
) -> StopRead:
    stop = await stops_repo.get_stop(session, stop_id)
    if stop is None:
        raise NotFoundError(f"Stop {stop_id} not found.")
    return stop_to_read(stop)
