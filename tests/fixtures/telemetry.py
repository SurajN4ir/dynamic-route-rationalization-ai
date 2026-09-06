"""Deterministic telemetry event factory - see
docs/architecture/TASK204_DESIGN.md §21. No real phones, GPS services, or
network access; every value is caller-controlled so tests are
reproducible (same inputs, same result, every run).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from geoalchemy2.shape import from_shape
from shapely.geometry import Point

from app.models.telemetry import Telemetry
from app.schemas.telemetry import TelemetryIngestRequest, TelemetrySource


def make_telemetry_event(
    vehicle_id: uuid.UUID,
    *,
    lat: float = 10.0,
    lon: float = 10.0,
    ts: datetime,
    speed_mps: float = 5.0,
    heading_deg: float | None = None,
    accuracy_m: float | None = None,
    source: TelemetrySource = "synthetic",
) -> TelemetryIngestRequest:
    return TelemetryIngestRequest(
        vehicle_id=vehicle_id,
        timestamp=ts,
        latitude=lat,
        longitude=lon,
        speed_mps=speed_mps,
        heading_deg=heading_deg,
        accuracy_m=accuracy_m,
        source=source,
    )


def make_telemetry_row(
    vehicle_id: uuid.UUID,
    *,
    ts: datetime,
    lat: float = 10.0,
    lon: float = 10.0,
    speed_mps: float = 5.0,
    road_segment_id: uuid.UUID | None = None,
    source: TelemetrySource = "synthetic",
    **kwargs: object,
) -> Telemetry:
    """A `Telemetry` ORM row ready for `session.add()`, bypassing
    `app.telemetry.pipeline` entirely - for ml/common's data-layer tests,
    which need real rows in the table but not TASK-204's
    validation/idempotency/Redis-cache machinery (already tested in
    tests/integration/test_telemetry_pipeline.py)."""
    return Telemetry(
        vehicle_id=vehicle_id,
        ts=ts,
        location=from_shape(Point(lon, lat), srid=4326),
        speed_mps=speed_mps,
        road_segment_id=road_segment_id,
        source=source,
        **kwargs,  # type: ignore[arg-type]
    )
