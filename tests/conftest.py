"""Shared pytest fixtures.

Test environment variables are set here, before anything imports `app.*`,
so app.core.config.get_settings() (which is lru_cache'd) picks them up on
its first call rather than caching whatever a developer's local .env
happens to contain. This must stay the first thing pytest imports -
conftest.py collection order guarantees that for everything under tests/.
"""

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://aura:aura_dev_password@localhost:5432/aura_test"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
os.environ.setdefault("ENVIRONMENT", "ci")
os.environ.setdefault("LOG_JSON", "false")

from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.cache.redis import redis_manager
from app.db.session import dispose_engine
from app.main import app


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest_asyncio.fixture(autouse=True)
async def _reset_shared_async_connections() -> AsyncIterator[None]:
    """Tear down the process-lifetime DB engine and Redis pool after every
    test.

    app.db.session.get_engine() and app.cache.redis.redis_manager are
    deliberately singletons that live for the whole application process
    (see their module docstrings) - correct for the real app, which runs
    forever on one event loop. pytest-asyncio, by default, gives every
    `async def test_...` its own event loop
    (asyncio_default_fixture_loop_scope is function-scoped here). Without
    this reset, a connection pooled by one test stays bound to that test's
    (now-closed) event loop and breaks the next test that reuses the
    cached engine/pool - a real cross-event-loop connection leak, not a
    hypothetical one. Resetting after each test forces a fresh
    engine/pool bound to whichever loop the next test actually runs on.
    """
    yield
    await dispose_engine()
    await redis_manager.disconnect()
