from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel

from app.models.geo import geometry_to_geojson_required
from app.schemas.geo import GeoJSONPoint

if TYPE_CHECKING:
    from app.models.stop import Stop


class StopRead(BaseModel):
    id: uuid.UUID
    code: str
    name: str | None
    location: GeoJSONPoint
    capacity_hint: int | None
    source: str
    source_id: str | None
    created_at: datetime
    updated_at: datetime


def stop_to_read(stop: Stop) -> StopRead:
    return StopRead(
        id=stop.id,
        code=stop.code,
        name=stop.name,
        location=GeoJSONPoint(**geometry_to_geojson_required(stop.location)),
        capacity_hint=stop.capacity_hint,
        source=stop.source,
        source_id=stop.source_id,
        created_at=stop.created_at,
        updated_at=stop.updated_at,
    )
