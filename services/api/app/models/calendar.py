"""ServiceCalendar - GTFS calendar.txt-equivalent: which days of the week
a service pattern runs, within a date range. Deliberately does not model
calendar_dates.txt-style exceptions (single-date add/remove overrides) -
out of scope for Phase 2's foundation; add a `service_calendar_exceptions`
table later if/when something actually needs it.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, CheckConstraint, Date, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ServiceCalendar(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "service_calendars"
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="ck_service_calendars_date_range"),
    )

    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    monday: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    tuesday: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    wednesday: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    thursday: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    friday: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    saturday: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    sunday: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
