"""The /readyz endpoint must honestly reflect actual dependency state,
whatever that state is in the current environment - see
app/api/health.py and docs/architecture/02-non-functional-requirements.md
2.3.
"""

from httpx import AsyncClient

from app.cache.redis import redis_manager
from app.db.session import check_database_connection


async def test_readyz_reflects_actual_dependency_state(client: AsyncClient) -> None:
    database_ok = await check_database_connection()
    redis_ok = await redis_manager.ping()

    response = await client.get("/readyz")
    body = response.json()

    expected_status = 200 if (database_ok and redis_ok) else 503
    assert response.status_code == expected_status
    assert body["checks"]["database"] == ("ok" if database_ok else "unavailable")
    assert body["checks"]["redis"] == ("ok" if redis_ok else "unavailable")
