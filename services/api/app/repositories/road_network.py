"""Data access for the road network (Road, RoadSegment, Intersection).

Thin, directly-testable functions - no business logic beyond querying;
endpoints call these rather than building queries inline (doc 13's
"repository operations" testing requirement targets this module).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.road_network import Road, RoadSegment


async def list_roads(session: AsyncSession) -> list[Road]:
    result = await session.execute(select(Road).order_by(Road.name))
    return list(result.scalars().all())


async def get_road(session: AsyncSession, road_id: uuid.UUID) -> Road | None:
    stmt = select(Road).where(Road.id == road_id).options(selectinload(Road.segments))
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_road_segment(session: AsyncSession, segment_id: uuid.UUID) -> RoadSegment | None:
    result = await session.execute(select(RoadSegment).where(RoadSegment.id == segment_id))
    return result.scalar_one_or_none()
