"""Redis connection management.

A single connection-pool-backed manager, reused across requests. Phase 1
only needs ping/get/set-level connectivity for the readiness check; the
same manager is the intended home for the Streams/pub-sub helpers that
docs/architecture/06-realtime-event-contracts.md describes for later
phases - do not build those yet, just keep the seam here.
"""

from __future__ import annotations

import redis.asyncio as redis


class RedisManager:
    def __init__(self, url: str) -> None:
        self._url = url
        self._pool: redis.ConnectionPool | None = None

    def connect(self) -> None:
        if self._pool is None:
            self._pool = redis.ConnectionPool.from_url(self._url, decode_responses=True)

    async def disconnect(self) -> None:
        if self._pool is not None:
            await self._pool.disconnect()
            self._pool = None

    @property
    def client(self) -> redis.Redis:
        if self._pool is None:
            self.connect()
        return redis.Redis(connection_pool=self._pool)

    async def ping(self) -> bool:
        try:
            return bool(await self.client.ping())
        except Exception:
            return False


def _build_manager() -> RedisManager:
    # Imported lazily so importing this module doesn't require settings to
    # already be configured (keeps import order flexible for tests).
    from app.core.config import get_settings

    return RedisManager(get_settings().redis_url)


redis_manager = _build_manager()


async def get_redis() -> redis.Redis:
    """FastAPI dependency returning a Redis client bound to the shared pool."""
    return redis_manager.client
