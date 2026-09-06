"""Static, canonical-network-derived features - see
docs/architecture/TASK205_DESIGN.md §3.

Bulk-loaded once per dataset-generation run (TASK-205 §20 - avoid a query
per row), not per feature row. Intersection connectivity reuses TASK-203's
already-built, already-tested `nx.MultiDiGraph` (`app.graph.builder`)
rather than re-deriving degree from raw SQL - exactly the "use the graph
for computational lookup where appropriate" TASK-204's own design doc
anticipated for future consumers.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.graph.builder import build_road_graph
from app.models.road_network import RoadSegment


@dataclass(frozen=True, slots=True)
class StaticSegmentFeatures:
    road_segment_id: uuid.UUID
    length_m: float | None
    road_class: str | None
    lanes: int | None
    maxspeed_kph: float | None
    is_oneway: bool
    start_intersection_degree: int | None
    end_intersection_degree: int | None


async def load_static_segment_features(
    session: AsyncSession,
) -> dict[uuid.UUID, StaticSegmentFeatures]:
    """One query for every RoadSegment's own columns, plus one TASK-203
    graph build for connectivity - never one query per segment."""
    graph_result = await build_road_graph(session)
    graph = graph_result.graph

    stmt = select(
        RoadSegment.id,
        RoadSegment.length_m,
        RoadSegment.road_class,
        RoadSegment.lanes,
        RoadSegment.maxspeed_kph,
        RoadSegment.is_oneway,
        RoadSegment.start_intersection_id,
        RoadSegment.end_intersection_id,
    ).order_by(RoadSegment.id)
    result = await session.execute(stmt)

    features: dict[uuid.UUID, StaticSegmentFeatures] = {}
    for row in result.all():
        start_degree = (
            graph.degree(row.start_intersection_id)
            if graph.has_node(row.start_intersection_id)
            else None
        )
        end_degree = (
            graph.degree(row.end_intersection_id)
            if graph.has_node(row.end_intersection_id)
            else None
        )
        features[row.id] = StaticSegmentFeatures(
            road_segment_id=row.id,
            length_m=row.length_m,
            road_class=row.road_class,
            lanes=row.lanes,
            maxspeed_kph=row.maxspeed_kph,
            is_oneway=row.is_oneway,
            start_intersection_degree=start_degree,
            end_intersection_degree=end_degree,
        )
    return features
