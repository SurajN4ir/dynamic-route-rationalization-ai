"""Telemetry ingestion endpoint - see docs/architecture/TASK204_DESIGN.md
§11. Unauthenticated for now - see the design doc §15 for why (no auth
infrastructure exists anywhere in this codebase yet, and this task's
brief explicitly says not to build one; ARCHITECTURE_REVIEW.md §12 item 4
already flagged this exact decision as deferred, not resolved here)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

import redis.asyncio as redis
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.redis import get_redis
from app.core.config import get_settings
from app.core.exceptions import UnprocessableEntityError
from app.db.session import get_db
from app.schemas.telemetry import TelemetryIngestRequest, TelemetryIngestResponse
from app.telemetry.pipeline import TelemetryRejected, UnknownVehicleError, ingest_telemetry

router = APIRouter(tags=["telemetry"])


@router.post(
    "/telemetry", response_model=TelemetryIngestResponse, status_code=status.HTTP_202_ACCEPTED
)
async def post_telemetry(
    payload: TelemetryIngestRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    redis_client: Annotated[redis.Redis, Depends(get_redis)],
) -> TelemetryIngestResponse:
    settings = get_settings()
    try:
        result = await ingest_telemetry(
            session,
            redis_client,
            payload,
            now=datetime.now(UTC),
            max_speed_mps=settings.telemetry_max_speed_mps,
            max_clock_skew_past_s=settings.telemetry_max_clock_skew_past_s,
            max_clock_skew_future_s=settings.telemetry_max_clock_skew_future_s,
            segment_search_radius_m=settings.telemetry_segment_search_radius_m,
            state_cache_ttl_s=settings.telemetry_state_cache_ttl_s,
        )
    except TelemetryRejected as exc:
        raise UnprocessableEntityError(
            "Telemetry rejected.", details={"errors": exc.reasons}
        ) from exc
    except UnknownVehicleError as exc:
        raise UnprocessableEntityError(str(exc), details={"code": "unknown_vehicle"}) from exc

    await session.commit()

    return TelemetryIngestResponse(
        status=result.status,  # type: ignore[arg-type]
        telemetry_id=result.telemetry_id,
        state_updated=result.state_updated,
        road_segment_id=result.road_segment_id,
        reason=result.reason,
    )
