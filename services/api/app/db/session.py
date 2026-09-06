"""Async database engine and session management.

One engine per process, created lazily so tests can set DATABASE_URL before
first use. See docs/architecture/04-data-model.md for the schema this will
serve once Phase 2 adds domain models, and
docs/architecture/02-non-functional-requirements.md 2.1 for the latency
budget this pool sizing should stay compatible with.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        echo=settings.database_echo,
        pool_pre_ping=True,
        pool_size=settings.database_pool_size,
    )


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a request-scoped session."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        yield session


async def check_database_connection() -> bool:
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def dispose_engine() -> None:
    """Close pooled connections and drop the cached engine/session factory.

    Called from the app lifespan's shutdown phase, and from tests that need
    a fresh engine after changing DATABASE_URL mid-run.
    """
    await get_engine().dispose()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
