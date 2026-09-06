from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.route import Route, RouteStop


async def list_routes(session: AsyncSession) -> list[Route]:
    result = await session.execute(select(Route).order_by(Route.code))
    return list(result.scalars().all())


async def get_route(session: AsyncSession, route_id: uuid.UUID) -> Route | None:
    result = await session.execute(select(Route).where(Route.id == route_id))
    return result.scalar_one_or_none()


async def get_route_stops(session: AsyncSession, route_id: uuid.UUID) -> list[RouteStop] | None:
    """Ordered stops for a route, or None if the route itself doesn't
    exist (distinct from a route that exists but has zero stops, which
    returns an empty list) - callers use this to decide 404 vs 200 []."""
    route = await get_route(session, route_id)
    if route is None:
        return None

    stmt = (
        select(RouteStop)
        .where(RouteStop.route_id == route_id)
        .options(selectinload(RouteStop.stop))
        .order_by(RouteStop.sequence)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
