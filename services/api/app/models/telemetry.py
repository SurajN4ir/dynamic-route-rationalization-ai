"""Vehicle GPS telemetry - see docs/architecture/TASK204_DESIGN.md.

Append-only history: every valid, non-duplicate sample is kept forever
here (doc 15.6's retention guidance is documented, not enforced by
deletion - see the design doc §16). This is why it does *not* use
`UUIDPrimaryKeyMixin`/`TimestampMixin` (both meant for mutable domain
rows, per mixins.py's own note pointing at this exact table) - a bigserial
`id` and a single `created_at` are enough for a row that is never updated.

`road_segment_id`/`segment_distance_m`/`segment_progress` are a *derived*
nearest-road-segment association computed at ingestion time (TASK-204
§7/§8) - not a claim of true map-matching, and never written back into
`road_segments` itself (PostGIS's canonical network stays read-only from
telemetry's perspective, same principle as TASK-203's graph).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from geoalchemy2 import Geometry, WKBElement
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

_TELEMETRY_SOURCE_VALUES = ("phone", "sumo", "synthetic")


class Telemetry(Base):
    __tablename__ = "telemetry"
    __table_args__ = (
        CheckConstraint(f"source IN {_TELEMETRY_SOURCE_VALUES}", name="ck_telemetry_source"),
        CheckConstraint("speed_mps >= 0", name="ck_telemetry_speed_non_negative"),
        CheckConstraint(
            "heading_deg IS NULL OR (heading_deg >= 0 AND heading_deg < 360)",
            name="ck_telemetry_heading_range",
        ),
        CheckConstraint(
            "segment_progress IS NULL OR (segment_progress >= 0 AND segment_progress <= 1)",
            name="ck_telemetry_segment_progress_range",
        ),
        CheckConstraint(
            "accuracy_m IS NULL OR accuracy_m >= 0", name="ck_telemetry_accuracy_non_negative"
        ),
        UniqueConstraint("vehicle_id", "ts", "source", name="uq_telemetry_vehicle_ts_source"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False
    )
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    location: Mapped[WKBElement] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=False), nullable=False
    )
    speed_mps: Mapped[float] = mapped_column(Float, nullable=False)
    heading_deg: Mapped[float | None] = mapped_column(Float, nullable=True)
    accuracy_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    road_segment_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("road_segments.id", ondelete="SET NULL"), nullable=True
    )
    segment_distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    segment_progress: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
