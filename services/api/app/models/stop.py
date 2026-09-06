"""Stop - extends docs/architecture/04-data-model.md `stops` with source
tracking (name, source, source_id) needed for idempotent OSM/GTFS
ingestion in a later task. `code`/`location`/`capacity_hint` are
unchanged from doc 04.
"""

from __future__ import annotations

from geoalchemy2 import Geometry, WKBElement
from sqlalchemy import CheckConstraint, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

_SOURCE_VALUES = ("osm", "gtfs", "manual")


class Stop(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "stops"
    __table_args__ = (
        CheckConstraint(f"source IN {_SOURCE_VALUES}", name="ck_stops_source"),
        # A plain UNIQUE constraint on a nullable column allows any number
        # of NULLs in Postgres (NULL <> NULL) - this is exactly the
        # idempotency behavior wanted: "unique when a source_id is known,
        # unconstrained for manually created stops with no external id."
        UniqueConstraint("source", "source_id", name="uq_stops_source_source_id"),
    )

    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[WKBElement] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=False), nullable=False
    )
    capacity_hint: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default="manual")
    source_id: Mapped[str | None] = mapped_column(Text, nullable=True)
