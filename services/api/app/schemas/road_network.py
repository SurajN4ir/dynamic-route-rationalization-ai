from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel

from app.models.geo import geometry_to_geojson_required
from app.schemas.geo import GeoJSONLineString, GeoJSONPoint

if TYPE_CHECKING:
    from app.models.road_network import Road, RoadSegment


class IntersectionRead(BaseModel):
    id: uuid.UUID
    location: GeoJSONPoint
    source: str
    osm_node_id: int | None
    created_at: datetime
    updated_at: datetime


class RoadSegmentRead(BaseModel):
    id: uuid.UUID
    road_id: uuid.UUID | None
    start_intersection_id: uuid.UUID
    end_intersection_id: uuid.UUID
    geometry: GeoJSONLineString
    length_m: float | None
    is_oneway: bool
    road_class: str | None
    source: str
    osm_way_id: int | None
    created_at: datetime
    updated_at: datetime


class RoadRead(BaseModel):
    id: uuid.UUID
    name: str | None
    road_class: str | None
    source: str
    created_at: datetime
    updated_at: datetime


class RoadWithSegmentsRead(RoadRead):
    segments: list[RoadSegmentRead]


def road_segment_to_read(segment: RoadSegment) -> RoadSegmentRead:
    return RoadSegmentRead(
        id=segment.id,
        road_id=segment.road_id,
        start_intersection_id=segment.start_intersection_id,
        end_intersection_id=segment.end_intersection_id,
        geometry=GeoJSONLineString(**geometry_to_geojson_required(segment.geometry)),
        length_m=segment.length_m,
        is_oneway=segment.is_oneway,
        road_class=segment.road_class,
        source=segment.source,
        osm_way_id=segment.osm_way_id,
        created_at=segment.created_at,
        updated_at=segment.updated_at,
    )


def road_to_read(road: Road) -> RoadRead:
    return RoadRead(
        id=road.id,
        name=road.name,
        road_class=road.road_class,
        source=road.source,
        created_at=road.created_at,
        updated_at=road.updated_at,
    )


def road_to_read_with_segments(road: Road) -> RoadWithSegmentsRead:
    return RoadWithSegmentsRead(
        **road_to_read(road).model_dump(),
        segments=[road_segment_to_read(s) for s in road.segments],
    )
