"""Physical road network topology: Intersection, Road, RoadSegment.

Architectural principle (Phase 2 decision, see
docs/architecture/PHASE2_DESIGN.md): PostGIS is the system of record for
this topology. An in-memory NetworkX/OSMnx graph used by later routing
work is a *derived* representation rebuilt from these tables, never the
source of truth. OSM is an input source (via `source`/`osm_*_id` columns
below), not the permanent domain model.

Road vs RoadSegment: `Road` is a human-meaningful named road (e.g. "MG
Road"), which may be composed of many OSM ways / topological pieces.
`RoadSegment` is the routable unit - a single edge between two
`Intersection`s, with its own geometry. `road_id` is nullable because a
segment can exist before it's been grouped under a named road (or may
never need to be, e.g. an unnamed service lane).
"""

from __future__ import annotations

import uuid

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

_SOURCE_VALUES = ("osm", "manual")


class Intersection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A node in the road graph: an intersection, dead-end, or any point
    where road topology needs a vertex. Every RoadSegment starts and ends
    at one of these."""

    __tablename__ = "intersections"
    __table_args__ = (
        CheckConstraint(f"source IN {_SOURCE_VALUES}", name="ck_intersections_source"),
        UniqueConstraint("osm_node_id", name="uq_intersections_osm_node_id"),
    )

    location: Mapped[str] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=False), nullable=False
    )
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default="manual")
    # Nullable + unique (not composite with source, since only OSM sourced
    # rows have this populated at all) - the idempotency key TASK-202's OSM
    # ingestion re-runs against: "have we already created a node for this
    # OSM node id?"
    osm_node_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    segments_starting_here: Mapped[list[RoadSegment]] = relationship(
        "RoadSegment",
        foreign_keys="RoadSegment.start_intersection_id",
        back_populates="start_intersection",
    )
    segments_ending_here: Mapped[list[RoadSegment]] = relationship(
        "RoadSegment",
        foreign_keys="RoadSegment.end_intersection_id",
        back_populates="end_intersection",
    )


class Road(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A named road, aggregating one or more RoadSegments. Optional layer
    - a segment need not belong to a Road (see RoadSegment.road_id)."""

    __tablename__ = "roads"
    __table_args__ = (CheckConstraint(f"source IN {_SOURCE_VALUES}", name="ck_roads_source"),)

    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    road_class: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default="manual")

    segments: Mapped[list[RoadSegment]] = relationship("RoadSegment", back_populates="road")


class RoadSegment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The routable unit of the road network: one edge between two
    Intersections, with its own line geometry."""

    __tablename__ = "road_segments"
    __table_args__ = (
        CheckConstraint(f"source IN {_SOURCE_VALUES}", name="ck_road_segments_source"),
        UniqueConstraint("osm_way_id", name="uq_road_segments_osm_way_id"),
    )

    road_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("roads.id", ondelete="SET NULL"), nullable=True
    )
    start_intersection_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("intersections.id", ondelete="RESTRICT"), nullable=False
    )
    end_intersection_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("intersections.id", ondelete="RESTRICT"), nullable=False
    )
    geometry: Mapped[str] = mapped_column(
        Geometry(geometry_type="LINESTRING", srid=4326, spatial_index=False), nullable=False
    )
    # Cached length in meters. Computable via ST_Length(geography(geometry))
    # on demand; stored too because routing (later phases) reads it on
    # every edge weight calculation and shouldn't recompute it per query.
    length_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_oneway: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    road_class: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default="manual")
    osm_way_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    road: Mapped[Road | None] = relationship("Road", back_populates="segments")
    start_intersection: Mapped[Intersection] = relationship(
        "Intersection",
        foreign_keys=[start_intersection_id],
        back_populates="segments_starting_here",
    )
    end_intersection: Mapped[Intersection] = relationship(
        "Intersection", foreign_keys=[end_intersection_id], back_populates="segments_ending_here"
    )
