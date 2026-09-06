"""Real database connectivity checks.

These need an actual Postgres+PostGIS instance (docker compose, or CI's
service container) and migrations already applied. They skip - rather than
fail - when no database is reachable, so `pytest` still runs cleanly on a
machine that hasn't started the stack; see docs/architecture/13-testing-
strategy.md. CI always has the service containers, so there this is a real
assertion, not a skip.
"""

import pytest
from sqlalchemy import text

from app.db.session import get_engine


async def _require_database() -> None:
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"database not reachable in this environment: {exc}")


async def test_database_is_reachable() -> None:
    await _require_database()

    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        assert result.scalar() == 1


async def test_postgis_extension_is_enabled() -> None:
    await _require_database()

    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'postgis'")
        )
        row = result.first()

    assert row is not None, (
        "postgis extension is not enabled - run " "`alembic upgrade head` from services/api first"
    )
