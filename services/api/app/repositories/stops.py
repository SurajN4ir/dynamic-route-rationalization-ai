"""Data access for Stop, including the proximity query demonstrating
PostGIS spatial capability (FR-FUSE-02-adjacent: nearest-stop lookups)."""

from __future__ import annotations

import uuid

from geoalchemy2 import Geography
from sqlalchemy import cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stop import Stop


async def list_stops(session: AsyncSession, limit: int = 100, offset: int = 0) -> list[Stop]:
    stmt = select(Stop).order_by(Stop.code).limit(limit).offset(offset)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_stop(session: AsyncSession, stop_id: uuid.UUID) -> Stop | None:
    result = await session.execute(select(Stop).where(Stop.id == stop_id))
    return result.scalar_one_or_none()


async def find_stops_near(
    session: AsyncSession, lon: float, lat: float, radius_m: float, limit: int = 20
) -> list[Stop]:
    """Stops within `radius_m` meters of (lon, lat), nearest first.

    Casts to `geography` so ST_DWithin/ST_Distance operate in meters
    rather than degrees - the standard PostGIS pattern for accurate
    distance queries on SRID 4326 data (doc 04 uses geometry(..., 4326)
    everywhere; geography casting is the query-time concern, not a
    schema change).
    """
    point = func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326)
    point_geog = cast(point, Geography)
    location_geog = cast(Stop.location, Geography)

    stmt = (
        select(Stop)
        .where(func.ST_DWithin(location_geog, point_geog, radius_m))
        .order_by(func.ST_Distance(location_geog, point_geog))
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
