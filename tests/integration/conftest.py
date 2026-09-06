"""Transactional test isolation for transportation-domain integration
tests.

Each test gets its own outer transaction on a dedicated connection; the
session is bound to that connection with `join_transaction_mode=
"create_savepoint"` so test code can call `session.commit()` (exercising
real commit-based code paths, e.g. the seed script) without it escaping
the outer transaction - everything is rolled back in the fixture's
teardown, so tests never leave rows behind for each other regardless of
execution order.

These tests need a real Postgres/PostGIS connection (they exercise actual
constraints and spatial queries, not something a mock could stand in
for - doc 13's "use the real PostGIS/Redis-backed integration environment
where appropriate"). If the database isn't reachable, they skip - the
same convention as tests/integration/test_db_connectivity.py.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.session import get_db, get_engine
from app.main import app


@pytest_asyncio.fixture
async def db_session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """The same rolled-back-transaction isolation as `db_session`, but
    exposed as a factory rather than one session - lets a test stand in
    for code (like the ingestion CLI) that creates its own session via
    `get_session_factory()` and calls commit()/rollback() on it, while
    still confining everything to one outer transaction that never
    survives the test."""
    engine = get_engine()
    # Establishing the connection is itself the reachability check - don't
    # run a query on it first, or SQLAlchemy's autobegin conflicts with the
    # explicit conn.begin() below ("Transaction() object via begin() or
    # autobegin" InvalidRequestError).
    try:
        conn = await engine.connect()
    except Exception as exc:
        pytest.skip(f"database not reachable in this environment: {exc}")
        return
    trans = await conn.begin()
    session_factory = async_sessionmaker(
        bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    try:
        yield session_factory
    finally:
        await trans.rollback()
        await conn.close()


@pytest_asyncio.fixture
async def db_session(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    session = db_session_factory()
    try:
        yield session
    finally:
        await session.close()


@pytest_asyncio.fixture
async def api_client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """An HTTP client for `app` whose DB dependency is overridden to use
    the same isolated, rolled-back transaction as `db_session` - data
    seeded via db_session is visible to requests made through this
    client, and none of it survives the test."""

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
