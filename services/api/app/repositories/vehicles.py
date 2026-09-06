from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.vehicle import Vehicle


async def list_vehicles(session: AsyncSession, limit: int = 100, offset: int = 0) -> list[Vehicle]:
    stmt = select(Vehicle).order_by(Vehicle.external_code).limit(limit).offset(offset)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_vehicle(session: AsyncSession, vehicle_id: uuid.UUID) -> Vehicle | None:
    result = await session.execute(select(Vehicle).where(Vehicle.id == vehicle_id))
    return result.scalar_one_or_none()
