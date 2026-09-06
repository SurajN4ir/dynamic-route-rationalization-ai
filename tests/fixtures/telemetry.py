"""Deterministic telemetry event factory - see
docs/architecture/TASK204_DESIGN.md §21. No real phones, GPS services, or
network access; every value is caller-controlled so tests are
reproducible (same inputs, same result, every run).
"""

from __future__ import annotations

import uuid
from datetime import datetime

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
