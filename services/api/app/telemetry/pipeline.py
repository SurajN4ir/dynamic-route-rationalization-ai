"""Telemetry ingestion pipeline orchestrator - see
docs/architecture/TASK204_DESIGN.md §2 for the full stage diagram:

parse (FastAPI/Pydantic, before this module runs) -> validate -> check
known vehicle -> deduplicate -> segment association -> persist -> ordering
check -> update current state -> publish.

Mirrors app/ingestion/osm/pipeline.py's shape: this module owns *what*
happens; the caller's session controls the transaction (the API endpoint
commits after a successful call). Redis failures are caught here and
degrade to "history persisted, cache not updated" rather than failing the
whole request - Postgres is the durable guarantee (TASK-204 §11/§26);
Redis is a best-effort fast path.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

import redis.asyncio as redis
from geoalchemy2.shape import from_shape
from shapely.geometry import Point
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.telemetry import Telemetry
from app.models.vehicle import Vehicle
from app.repositories.telemetry import get_latest_telemetry
from app.schemas.telemetry import TelemetryIngestRequest
from app.telemetry.freshness import is_newer
from app.telemetry.publisher import publish_state_update
from app.telemetry.segment_association import find_nearest_segment
from app.telemetry.state import CurrentVehicleState, read_cached_state
from app.telemetry.validation import validate_fields

logger = logging.getLogger(__name__)


class TelemetryRejected(Exception):
    """Raised for a deterministically-invalid event. Carries the reasons
    so the API layer can report them; never raised for a duplicate or
    out-of-order event, both of which are valid, accepted outcomes."""

    def __init__(self, reasons: list[str]) -> None:
        self.reasons = reasons
        super().__init__("; ".join(reasons))


class UnknownVehicleError(Exception):
    """The referenced vehicle_id has no matching `vehicles` row."""


@dataclass(frozen=True, slots=True)
class IngestResult:
    status: str  # "accepted" | "duplicate"
    telemetry_id: int | None
    state_updated: bool
    road_segment_id: uuid.UUID | None
    reason: str | None


async def _vehicle_exists(session: AsyncSession, vehicle_id: uuid.UUID) -> bool:
    result = await session.execute(select(Vehicle.id).where(Vehicle.id == vehicle_id))
    return result.scalar_one_or_none() is not None


async def _is_duplicate(
    session: AsyncSession, vehicle_id: uuid.UUID, ts: datetime, source: str
) -> bool:
    stmt = select(Telemetry.id).where(
        Telemetry.vehicle_id == vehicle_id, Telemetry.ts == ts, Telemetry.source == source
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


async def _latest_known_ts(
    session: AsyncSession, redis_client: redis.Redis | None, vehicle_id: uuid.UUID
) -> datetime | None:
    if redis_client is not None:
        try:
            cached = await read_cached_state(redis_client, vehicle_id)
            if cached is not None:
                return cached.ts
        except Exception:
            logger.warning("redis unavailable for ordering check; falling back to Postgres")

    latest_row = await get_latest_telemetry(session, vehicle_id)
    return latest_row.ts if latest_row is not None else None


async def ingest_telemetry(
    session: AsyncSession,
    redis_client: redis.Redis | None,
    payload: TelemetryIngestRequest,
    *,
    now: datetime,
    max_speed_mps: float,
    max_clock_skew_past_s: int,
    max_clock_skew_future_s: int,
    segment_search_radius_m: float,
    state_cache_ttl_s: int,
) -> IngestResult:
    reasons = validate_fields(
        payload,
        now=now,
        max_speed_mps=max_speed_mps,
        max_clock_skew_past_s=max_clock_skew_past_s,
        max_clock_skew_future_s=max_clock_skew_future_s,
    )
    if reasons:
        logger.info(
            "telemetry rejected", extra={"vehicle_id": str(payload.vehicle_id), "reasons": reasons}
        )
        raise TelemetryRejected(reasons)

    if not await _vehicle_exists(session, payload.vehicle_id):
        logger.info(
            "telemetry rejected: unknown vehicle", extra={"vehicle_id": str(payload.vehicle_id)}
        )
        raise UnknownVehicleError(f"Vehicle {payload.vehicle_id} not found.")

    if await _is_duplicate(session, payload.vehicle_id, payload.timestamp, payload.source):
        logger.info(
            "telemetry duplicate event recognized",
            extra={"vehicle_id": str(payload.vehicle_id), "ts": payload.timestamp.isoformat()},
        )
        return IngestResult(
            status="duplicate",
            telemetry_id=None,
            state_updated=False,
            road_segment_id=None,
            reason="duplicate event",
        )

    # Captured before the insert below - once that row exists, a query for
    # "this vehicle's latest telemetry" would find the event being ingested
    # right now, comparing its timestamp to itself and never advancing state.
    previous_ts = await _latest_known_ts(session, redis_client, payload.vehicle_id)

    match = await find_nearest_segment(
        session, lon=payload.longitude, lat=payload.latitude, radius_m=segment_search_radius_m
    )
    if match is None:
        logger.info(
            "telemetry segment association found no candidate",
            extra={"vehicle_id": str(payload.vehicle_id)},
        )

    point = from_shape(Point(payload.longitude, payload.latitude), srid=4326)
    stmt = (
        pg_insert(Telemetry)
        .values(
            vehicle_id=payload.vehicle_id,
            ts=payload.timestamp,
            location=point,
            speed_mps=payload.speed_mps,
            heading_deg=payload.heading_deg,
            accuracy_m=payload.accuracy_m,
            source=payload.source,
            road_segment_id=match.road_segment_id if match else None,
            segment_distance_m=match.distance_m if match else None,
            segment_progress=match.progress if match else None,
        )
        .on_conflict_do_nothing(constraint="uq_telemetry_vehicle_ts_source")
        .returning(Telemetry.id)
    )
    result = await session.execute(stmt)
    inserted_id = result.scalar_one_or_none()

    if inserted_id is None:
        # Lost a race against a concurrent identical retry between the
        # _is_duplicate check and this insert - still a duplicate, not an
        # error (doc 06 §6.1a's guarantee holds regardless of timing).
        return IngestResult(
            status="duplicate",
            telemetry_id=None,
            state_updated=False,
            road_segment_id=None,
            reason="duplicate event (concurrent)",
        )

    state_updated = is_newer(payload.timestamp, previous_ts)

    if not state_updated:
        logger.info(
            "telemetry recorded but out-of-order; current state not advanced",
            extra={
                "vehicle_id": str(payload.vehicle_id),
                "event_ts": payload.timestamp.isoformat(),
                "current_state_ts": previous_ts.isoformat() if previous_ts else None,
            },
        )
        return IngestResult(
            status="accepted",
            telemetry_id=inserted_id,
            state_updated=False,
            road_segment_id=match.road_segment_id if match else None,
            reason="out-of-order: older than current state",
        )

    new_state = CurrentVehicleState(
        vehicle_id=payload.vehicle_id,
        latitude=payload.latitude,
        longitude=payload.longitude,
        speed_mps=payload.speed_mps,
        heading_deg=payload.heading_deg,
        ts=payload.timestamp,
        road_segment_id=match.road_segment_id if match else None,
        segment_distance_m=match.distance_m if match else None,
    )
    if redis_client is not None:
        try:
            await publish_state_update(redis_client, new_state, ttl_s=state_cache_ttl_s)
        except Exception:
            logger.warning(
                "redis unavailable for state publish; history persisted, cache not updated",
                extra={"vehicle_id": str(payload.vehicle_id)},
            )

    logger.info(
        "telemetry accepted, state updated",
        extra={"vehicle_id": str(payload.vehicle_id), "telemetry_id": inserted_id},
    )
    return IngestResult(
        status="accepted",
        telemetry_id=inserted_id,
        state_updated=True,
        road_segment_id=match.road_segment_id if match else None,
        reason=None,
    )
