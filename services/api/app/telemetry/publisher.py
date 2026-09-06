"""Internal state-update publication boundary - see
docs/architecture/TASK204_DESIGN.md §12.

Everything the ingestion pipeline needs to do after a telemetry event
advances a vehicle's current state goes through this one function. Today
that's just the Redis cache write; `app/cache/redis.py` already flags
itself as "the intended home for the Streams/pub-sub helpers... later
phases" and explicitly says not to build those yet, so this module is the
seam a future task attaches Redis Streams (or WebSocket fan-out) to,
without the ingestion pipeline itself needing to change.
"""

from __future__ import annotations

import redis.asyncio as redis

from app.telemetry.state import CurrentVehicleState, write_cached_state


async def publish_state_update(
    redis_client: redis.Redis, state: CurrentVehicleState, *, ttl_s: int
) -> None:
    await write_cached_state(redis_client, state, ttl_s=ttl_s)
