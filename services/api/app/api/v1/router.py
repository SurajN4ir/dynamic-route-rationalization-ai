"""Aggregates all /api/v1 endpoint routers.

Phase 2 adds the transportation domain foundation's read endpoints
(roads, stops, routes, vehicles) per docs/architecture/PHASE2_DESIGN.md.
Later phases add a router import + include_router line here per doc 05
section, not a restructure.
"""

from fastapi import APIRouter

from app.api.v1.endpoints import fleet, roads, routes, status, stops, telemetry, vehicles

api_router = APIRouter()
api_router.include_router(status.router)
api_router.include_router(roads.router)
api_router.include_router(roads.segments_router)
api_router.include_router(stops.router)
api_router.include_router(routes.router)
api_router.include_router(vehicles.router)
api_router.include_router(telemetry.router)
api_router.include_router(fleet.router)
