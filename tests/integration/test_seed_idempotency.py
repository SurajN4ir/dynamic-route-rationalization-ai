"""The dev seed script (app/db/seed.py) must be safe to run more than
once against the same database - required so `docker compose up` /
manual re-runs never duplicate fixture data."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.seed import seed_dev_data
from app.models.road_network import Road


async def test_seed_dev_data_is_idempotent(db_session: AsyncSession) -> None:
    await seed_dev_data(db_session)
    first_count = await db_session.scalar(
        select(func.count()).select_from(Road).where(Road.name == "DEV_MAIN_ST")
    )

    await seed_dev_data(db_session)
    second_count = await db_session.scalar(
        select(func.count()).select_from(Road).where(Road.name == "DEV_MAIN_ST")
    )

    assert first_count == 1
    assert second_count == 1
