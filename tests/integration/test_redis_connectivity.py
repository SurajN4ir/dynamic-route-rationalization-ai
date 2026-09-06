"""Real Redis connectivity checks - see tests/integration/test_db_connectivity.py
for the same skip-if-unreachable rationale.
"""

import pytest

from app.cache.redis import redis_manager


async def _require_redis() -> None:
    if not await redis_manager.ping():
        pytest.skip("redis not reachable in this environment")


async def test_redis_is_reachable() -> None:
    await _require_redis()

    assert await redis_manager.ping() is True


async def test_redis_set_get_roundtrip() -> None:
    await _require_redis()

    client = redis_manager.client
    key = "aura:phase1:selftest"
    try:
        await client.set(key, "ok", ex=30)
        value = await client.get(key)
        assert value == "ok"
    finally:
        await client.delete(key)
