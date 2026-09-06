"""Read-only endpoints for the road network (Road, RoadSegment).

Write access is deliberately not exposed here in Phase 2 - doc 05 doesn't
define transportation-entity write endpoints, and OSM/GTFS ingestion (a
later task) is the intended way these tables get populated, not a public
API. Seed/test data is created directly via the ORM (see
services/api/app/db/seed.py), not through HTTP.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.repositories import road_network as road_repo
from app.schemas.road_network import (
    RoadRead,
    RoadSegmentRead,
    RoadWithSegmentsRead,
    road_segment_to_read,
    road_to_read,
    road_to_read_with_segments,
)

router = APIRouter(prefix="/roads", tags=["road-network"])


@router.get("", response_model=list[RoadRead])
async def list_roads(session: Annotated[AsyncSession, Depends(get_db)]) -> list[RoadRead]:
    roads = await road_repo.list_roads(session)
    return [road_to_read(r) for r in roads]


@router.get("/{road_id}", response_model=RoadWithSegmentsRead)
async def get_road(
    road_id: uuid.UUID, session: Annotated[AsyncSession, Depends(get_db)]
) -> RoadWithSegmentsRead:
    road = await road_repo.get_road(session, road_id)
    if road is None:
        raise NotFoundError(f"Road {road_id} not found.")
    return road_to_read_with_segments(road)


segments_router = APIRouter(prefix="/road-segments", tags=["road-network"])


@segments_router.get("/{segment_id}", response_model=RoadSegmentRead)
async def get_road_segment(
    segment_id: uuid.UUID, session: Annotated[AsyncSession, Depends(get_db)]
) -> RoadSegmentRead:
    segment = await road_repo.get_road_segment(session, segment_id)
    if segment is None:
        raise NotFoundError(f"Road segment {segment_id} not found.")
    return road_segment_to_read(segment)
