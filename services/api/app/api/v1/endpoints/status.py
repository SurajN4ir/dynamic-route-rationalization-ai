"""Real (non-domain) service metadata.

Not a health check - a small, genuinely-true endpoint the frontend's system
status page reads (docs/architecture/01-functional-requirements.md does not
define this endpoint yet; it is infrastructure metadata, not a
transportation feature, so it does not need a doc 05 entry to justify
existing in Phase 1).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings

router = APIRouter(tags=["status"])


@router.get("/status")
async def service_status(
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
    }
