"""Vehicle and VehicleAssignment.

`Vehicle` extends docs/architecture/04-data-model.md `vehicles` with audit
timestamps and explicit CHECK constraints on the previously-freeform
`source`/`status` text columns.

`VehicleAssignment` is a new, Phase-2-scope, *static fleet-planning*
concept: which vehicle serves which route, for which ServiceCalendar
period - e.g. "BUS_07 serves Route 12 on weekdays from 2026-01-01". This
is deliberately independent of doc 04's `trips` table, which stays
untouched and remains Phase 3's real-time execution-tracking concern (a
specific journey instance, not a standing assignment). Confirmed via
architecture reconciliation before implementation - see
docs/architecture/PHASE2_DESIGN.md.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.calendar import ServiceCalendar
    from app.models.route import Route

_VEHICLE_SOURCE_VALUES = ("real", "simulated")
_VEHICLE_STATUS_VALUES = ("active", "spare", "maintenance")
_ASSIGNMENT_STATUS_VALUES = ("active", "ended")


class Vehicle(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "vehicles"
    __table_args__ = (
        CheckConstraint(f"source IN {_VEHICLE_SOURCE_VALUES}", name="ck_vehicles_source"),
        CheckConstraint(f"status IN {_VEHICLE_STATUS_VALUES}", name="ck_vehicles_status"),
    )

    external_code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default="real")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")

    assignments: Mapped[list[VehicleAssignment]] = relationship(
        "VehicleAssignment", back_populates="vehicle"
    )


class VehicleAssignment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "vehicle_assignments"
    __table_args__ = (
        CheckConstraint(
            f"status IN {_ASSIGNMENT_STATUS_VALUES}", name="ck_vehicle_assignments_status"
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from", name="ck_vehicle_assignments_date_range"
        ),
        UniqueConstraint(
            "vehicle_id",
            "route_id",
            "service_calendar_id",
            "valid_from",
            name="uq_vehicle_assignments_natural_key",
        ),
    )

    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("vehicles.id", ondelete="RESTRICT"), nullable=False
    )
    route_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("routes.id", ondelete="RESTRICT"), nullable=False
    )
    service_calendar_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("service_calendars.id", ondelete="RESTRICT"),
        nullable=False,
    )
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")

    vehicle: Mapped[Vehicle] = relationship("Vehicle", back_populates="assignments")
    route: Mapped[Route] = relationship("Route")
    service_calendar: Mapped[ServiceCalendar] = relationship("ServiceCalendar")
