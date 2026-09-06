"""Telemetry wire contract and current-state read shape - see
docs/architecture/TASK204_DESIGN.md §2/§8.

Deliberately narrower than doc 06 §6.1's original `VehicleTelemetry`
JSON shape: `route_id`/`trip_id` are dropped (see the design doc §13 for
why - `trips` was never built, and conflating "where is the vehicle" with
"what is it assigned to" is exactly what this task's brief says not to
do) and `occupancy` is dropped (a demand-prediction input, no consumer
exists yet - "every field must have a clear purpose").
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

TelemetrySource = Literal["phone", "sumo", "synthetic"]


class TelemetryIngestRequest(BaseModel):
    vehicle_id: uuid.UUID
    timestamp: datetime
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    speed_mps: float = Field(ge=0)
    heading_deg: float | None = Field(default=None, ge=0, lt=360)
    accuracy_m: float | None = Field(default=None, ge=0)
    source: TelemetrySource


class TelemetryIngestResponse(BaseModel):
    status: Literal["accepted", "duplicate"]
    telemetry_id: int | None
    state_updated: bool
    road_segment_id: uuid.UUID | None
    reason: str | None = None


class VehicleAssignmentSummary(BaseModel):
    route_id: uuid.UUID
    service_calendar_id: uuid.UUID


class VehicleStateRead(BaseModel):
    vehicle_id: uuid.UUID
    latitude: float
    longitude: float
    speed_mps: float
    heading_deg: float | None
    ts: datetime
    road_segment_id: uuid.UUID | None
    segment_distance_m: float | None
    freshness: Literal["live", "stale", "offline"]
    active_assignment: VehicleAssignmentSummary | None
