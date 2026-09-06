"""Matches docs/architecture/05-api-specification.md 5.3 (`/routes`,
`/routes/{route_id}/stops`) and the doc 12 Phase 2 exit criterion: "static
route/stop data for the demo network is queryable via /routes,
/routes/{id}/stops"."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.repositories import routes as routes_repo
from app.schemas.route import RouteRead, RouteStopRead, route_stop_to_read, route_to_read

router = APIRouter(prefix="/routes", tags=["routes"])


@router.get("", response_model=list[RouteRead])
async def list_routes(session: Annotated[AsyncSession, Depends(get_db)]) -> list[RouteRead]:
    routes = await routes_repo.list_routes(session)
    return [route_to_read(r) for r in routes]


@router.get("/{route_id}", response_model=RouteRead)
async def get_route(
    route_id: uuid.UUID, session: Annotated[AsyncSession, Depends(get_db)]
) -> RouteRead:
    route = await routes_repo.get_route(session, route_id)
    if route is None:
        raise NotFoundError(f"Route {route_id} not found.")
    return route_to_read(route)


@router.get("/{route_id}/stops", response_model=list[RouteStopRead])
async def get_route_stops(
    route_id: uuid.UUID, session: Annotated[AsyncSession, Depends(get_db)]
) -> list[RouteStopRead]:
    route_stops = await routes_repo.get_route_stops(session, route_id)
    if route_stops is None:
        raise NotFoundError(f"Route {route_id} not found.")
    return [route_stop_to_read(rs) for rs in route_stops]
