"""Application startup/shutdown lifecycle.

Connects the Redis pool eagerly on startup (so the first request doesn't
pay connection-setup cost and so a misconfigured REDIS_URL fails fast in
logs) and disposes both Redis and the database engine cleanly on shutdown.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.cache.redis import redis_manager
from app.db.session import dispose_engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("AURA API starting up")
    redis_manager.connect()
    try:
        yield
    finally:
        logger.info("AURA API shutting down")
        await redis_manager.disconnect()
        await dispose_engine()
