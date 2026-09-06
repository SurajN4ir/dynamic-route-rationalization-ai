"""vehicle telemetry history (TASK-204)

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-06

Architecture reconciliation finding (see docs/architecture/TASK204_DESIGN.md
§2/§9): doc 04's original `telemetry` table shape predates TASK-201/202/203
and does not match the schema this project actually committed to -
`trip_id`/`route_id` reference a `trips` table that was never created
(TASK-201 deliberately built `vehicle_assignments` instead, kept
independent of raw position telemetry - see PHASE2_DESIGN.md §2.3 and
TASK204_DESIGN.md §13), and `matched_edge_id` (text, "OSM edge id") predates
TASK-203's canonical graph, which keys everything by `road_segments.id`
(uuid), never a raw OSM way/edge id. This migration creates the table with
the corrected shape rather than the literal doc 04 v1.0 column list; doc 04
is updated in place to match (same pattern as migration 0003's correction).

Bigserial `id` + a single `created_at` (no `updated_at`) rather than the
usual `UUIDPrimaryKeyMixin`/`TimestampMixin` pair - this is exactly the
append-only, high-volume table `app/models/mixins.py` already anticipated
needing a different treatment for.
"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "telemetry",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("vehicle_id", PGUUID(as_uuid=True), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "location",
            geoalchemy2.Geometry(geometry_type="POINT", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("speed_mps", sa.Float(), nullable=False),
        sa.Column("heading_deg", sa.Float(), nullable=True),
        sa.Column("accuracy_m", sa.Float(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("road_segment_id", PGUUID(as_uuid=True), nullable=True),
        sa.Column("segment_distance_m", sa.Float(), nullable=True),
        sa.Column("segment_progress", sa.Float(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["vehicle_id"], ["vehicles.id"], name="fk_telemetry_vehicle_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["road_segment_id"],
            ["road_segments.id"],
            name="fk_telemetry_road_segment_id",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint("source IN ('phone', 'sumo', 'synthetic')", name="ck_telemetry_source"),
        sa.CheckConstraint("speed_mps >= 0", name="ck_telemetry_speed_non_negative"),
        sa.CheckConstraint(
            "heading_deg IS NULL OR (heading_deg >= 0 AND heading_deg < 360)",
            name="ck_telemetry_heading_range",
        ),
        sa.CheckConstraint(
            "segment_progress IS NULL OR (segment_progress >= 0 AND segment_progress <= 1)",
            name="ck_telemetry_segment_progress_range",
        ),
        sa.CheckConstraint(
            "accuracy_m IS NULL OR accuracy_m >= 0", name="ck_telemetry_accuracy_non_negative"
        ),
        sa.UniqueConstraint("vehicle_id", "ts", "source", name="uq_telemetry_vehicle_ts_source"),
    )
    op.create_index("ix_telemetry_location", "telemetry", ["location"], postgresql_using="gist")
    op.create_index("ix_telemetry_vehicle_id_ts", "telemetry", ["vehicle_id", "ts"])
    op.create_index("ix_telemetry_road_segment_id", "telemetry", ["road_segment_id"])


def downgrade() -> None:
    op.drop_table("telemetry")
