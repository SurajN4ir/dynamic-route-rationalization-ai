"""Liveness and readiness endpoints.

Unversioned and auth-exempt, per docs/architecture/05-api-specification.md
("JWT bearer auth on every endpoint except /auth/login and /healthz").

Liveness (/healthz) answers "is the process up" and never touches a
dependency - a slow/dead database must not make the container orchestrator
think the process itself is unhealthy. Readiness (/readyz) answers "can
this instance actually serve traffic" and checks every hard dependency;
Docker Compose / CI use it to gate on the stack actually being usable.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.cache.redis import redis_manager
from app.db.session import check_database_connection

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readiness(response: Response) -> dict[str, object]:
    database_ok = await check_database_connection()
    redis_ok = await redis_manager.ping()
    ready = database_ok and redis_ok

    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ok" if ready else "unavailable",
        "checks": {
            "database": "ok" if database_ok else "unavailable",
            "redis": "ok" if redis_ok else "unavailable",
        },
    }
