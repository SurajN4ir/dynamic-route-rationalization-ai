"""Route and RouteStop - extends docs/architecture/04-data-model.md.

`RouteStop`'s primary key is `(route_id, sequence)`, not
`(route_id, stop_id, sequence)` - this was already decided and justified
in the Phase 0 architecture review (docs/architecture/ARCHITECTURE_REVIEW.md
finding M2): sequence alone determines position along a route, so
including stop_id in the key would let two different stops occupy the
same sequence position, which is not a valid route. Implemented exactly
as that review specified, not redesigned here.

`Route.geometry` is nullable (a deviation from doc 04's literal column
list, which didn't mark it nullable) - a route can legitimately exist
before a computed path is available; requiring it NOT NULL would block
creating a route ahead of OSM ingestion/routing work landing in a later
task. Documented in docs/architecture/PHASE2_DESIGN.md.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from geoalchemy2 import Geometry
from sqlalchemy import CheckConstraint, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.stop import Stop

_SOURCE_VALUES = ("osm", "gtfs", "manual")


class Route(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "routes"
    __table_args__ = (
        CheckConstraint(f"source IN {_SOURCE_VALUES}", name="ck_routes_source"),
        UniqueConstraint("source", "source_id", name="uq_routes_source_source_id"),
    )

    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    geometry: Mapped[str | None] = mapped_column(
        Geometry(geometry_type="LINESTRING", srid=4326, spatial_index=False), nullable=True
    )
    direction: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default="manual")
    source_id: Mapped[str | None] = mapped_column(Text, nullable=True)

    route_stops: Mapped[list[RouteStop]] = relationship(
        "RouteStop",
        back_populates="route",
        order_by="RouteStop.sequence",
        cascade="all, delete-orphan",
    )


class RouteStop(TimestampMixin, Base):
    __tablename__ = "route_stops"
    __table_args__ = (CheckConstraint("sequence >= 0", name="ck_route_stops_sequence_nonnegative"),)

    route_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("routes.id", ondelete="CASCADE"), primary_key=True
    )
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True)
    stop_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("stops.id", ondelete="RESTRICT"), nullable=False
    )
    scheduled_offset_s: Mapped[int | None] = mapped_column(Integer, nullable=True)

    route: Mapped[Route] = relationship("Route", back_populates="route_stops")
    stop: Mapped[Stop] = relationship("Stop")
