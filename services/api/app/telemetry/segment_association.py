"""GPS position -> nearest canonical road segment - see
docs/architecture/TASK204_DESIGN.md §7.

This is deliberately **not** map matching. It answers "which RoadSegment
is geometrically closest to this point, within a search radius" - a
single nearest-neighbour spatial query - not "which path is the vehicle
actually most likely following given its trajectory and the road
topology" (that would need heading, recent history, and graph
connectivity, none of which this function looks at). Callers must not
present this as a map-matched position.

Reuses the exact `ST_DWithin`/`ST_Distance` + geography-cast pattern
`app/repositories/stops.py:find_stops_near` already established for
point-to-point proximity, extended to point-to-line.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from geoalchemy2 import Geography
from sqlalchemy import cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.road_network import RoadSegment


@dataclass(frozen=True, slots=True)
class SegmentMatch:
    road_segment_id: uuid.UUID
    distance_m: float
    progress: float  # 0..1 fraction along the segment, from ST_LineLocatePoint


async def find_nearest_segment(
    session: AsyncSession, *, lon: float, lat: float, radius_m: float
) -> SegmentMatch | None:
    """The nearest `RoadSegment` within `radius_m` of (lon, lat), or
    `None` if nothing qualifies - a normal, expected outcome (e.g. a GPS
    fix off any mapped road), not an error."""
    point = func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326)
    point_geog = cast(point, Geography)
    segment_geog = cast(RoadSegment.geometry, Geography)
    distance = func.ST_Distance(segment_geog, point_geog)
    # ST_LineLocatePoint operates on `geometry` (planar), not `geography` -
    # a degrees-based approximation, same known limitation already
    # documented for TASK-202's length estimate (not geodesic-precise, but
    # adequate for a fractional along-segment position at this scale).
    progress = func.ST_LineLocatePoint(RoadSegment.geometry, point)

    stmt = (
        select(RoadSegment.id, distance, progress)
        .where(func.ST_DWithin(segment_geog, point_geog, radius_m))
        .order_by(distance)
        .limit(1)
    )
    result = await session.execute(stmt)
    row = result.first()
    if row is None:
        return None
    segment_id, distance_m, progress_fraction = row
    return SegmentMatch(
        road_segment_id=segment_id, distance_m=float(distance_m), progress=float(progress_fraction)
    )
