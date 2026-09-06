from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel

from app.models.geo import geometry_to_geojson
from app.schemas.geo import GeoJSONLineString
from app.schemas.stop import StopRead, stop_to_read

if TYPE_CHECKING:
    from app.models.route import Route, RouteStop


class RouteRead(BaseModel):
    id: uuid.UUID
    code: str
    name: str | None
    geometry: GeoJSONLineString | None
    direction: str | None
    source: str
    source_id: str | None
    created_at: datetime
    updated_at: datetime


class RouteStopRead(BaseModel):
    route_id: uuid.UUID
    sequence: int
    stop_id: uuid.UUID
    scheduled_offset_s: int | None
    stop: StopRead


def route_to_read(route: Route) -> RouteRead:
    geojson = geometry_to_geojson(route.geometry)
    return RouteRead(
        id=route.id,
        code=route.code,
        name=route.name,
        geometry=GeoJSONLineString(**geojson) if geojson else None,
        direction=route.direction,
        source=route.source,
        source_id=route.source_id,
        created_at=route.created_at,
        updated_at=route.updated_at,
    )


def route_stop_to_read(route_stop: RouteStop) -> RouteStopRead:
    return RouteStopRead(
        route_id=route_stop.route_id,
        sequence=route_stop.sequence,
        stop_id=route_stop.stop_id,
        scheduled_offset_s=route_stop.scheduled_offset_s,
        stop=stop_to_read(route_stop.stop),
    )
