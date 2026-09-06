"""Aggregates all /api/v1 endpoint routers.

Empty of business endpoints in Phase 1 by design (no ingestion, prediction,
decision, or recommendation logic yet - see
docs/architecture/12-development-phases.md). Later phases add a router
import + include_router line here per doc 05 section, not a restructure.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import status

api_router = APIRouter()
api_router.include_router(status.router)
