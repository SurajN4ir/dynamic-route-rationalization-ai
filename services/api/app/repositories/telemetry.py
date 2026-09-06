"""Data access for Telemetry/VehicleAssignment reads that back the
real-time state API - see docs/architecture/TASK204_DESIGN.md §8/§9/§13.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.telemetry import Telemetry
from app.models.vehicle import VehicleAssignment


async def get_latest_telemetry(session: AsyncSession, vehicle_id: uuid.UUID) -> Telemetry | None:
    """The most recent telemetry row for a vehicle - the Postgres-durable
    source of truth a Redis-cache-miss/outage falls back to (TASK-204
    §11/§26)."""
    stmt = (
        select(Telemetry)
        .where(Telemetry.vehicle_id == vehicle_id)
        .order_by(Telemetry.ts.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_vehicle_ids_with_telemetry(session: AsyncSession) -> list[uuid.UUID]:
    """Vehicles that have ever reported telemetry - the population
    `GET /fleet` reports over. A vehicle that has never transmitted has no
    "state" to report at all, not an offline one (TASK-204 §9)."""
    stmt = select(Telemetry.vehicle_id).distinct()
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_active_assignment(
    session: AsyncSession, vehicle_id: uuid.UUID, as_of: date
) -> VehicleAssignment | None:
    """The vehicle's active fleet-planning assignment as of a date, if
    any - resolved on read, never stored on a telemetry row (TASK-204
    §13/§15: assignment and telemetry are separate concerns). Does not
    check the assignment's `ServiceCalendar` day-of-week bits - a
    documented simplification (TASK204_DESIGN.md §17), not a correctness
    claim about which specific day the assignment runs."""
    stmt = (
        select(VehicleAssignment)
        .where(
            VehicleAssignment.vehicle_id == vehicle_id,
            VehicleAssignment.status == "active",
            VehicleAssignment.valid_from <= as_of,
            (VehicleAssignment.valid_to.is_(None)) | (VehicleAssignment.valid_to >= as_of),
        )
        .order_by(VehicleAssignment.valid_from.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_segment_observation(
    session: AsyncSession, road_segment_id: uuid.UUID, window_s: int, *, now: datetime
) -> tuple[int, float | None]:
    """Observed-vehicle-count and mean speed for a road segment over the
    trailing `window_s` seconds ending at `now` - the "network state"
    concept TASK-204 §23 establishes. This is observed telemetry
    aggregation, not a traffic *prediction* - no model, no forecasting,
    nothing persisted. `now` is caller-supplied (not the DB server clock)
    for the same determinism reason the rest of this package always
    threads `now` through explicitly rather than reading a clock itself."""
    cutoff = now - timedelta(seconds=window_s)
    stmt = select(func.count(Telemetry.id), func.avg(Telemetry.speed_mps)).where(
        Telemetry.road_segment_id == road_segment_id, Telemetry.ts >= cutoff
    )
    result = await session.execute(stmt)
    count, avg_speed = result.one()
    return int(count), float(avg_speed) if avg_speed is not None else None
