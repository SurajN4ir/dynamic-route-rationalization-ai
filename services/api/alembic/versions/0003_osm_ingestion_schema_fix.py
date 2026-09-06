"""osm ingestion schema fix + road feature columns (TASK-202)

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-06

Architecture reconciliation finding (see docs/architecture/TASK202_DESIGN.md
§1): PHASE2_DESIGN.md §4 already specified that a single OSM way may split
into multiple RoadSegment rows at shared/junction nodes, but the migration
0002 committed under TASK-201 gave `road_segments` a bare UNIQUE constraint
on `osm_way_id` alone - which cannot hold once a way legitimately produces
more than one segment row. This migration corrects that gap before the
ingestion pipeline (which relies on way-splitting) is built:

- `road_segments.way_seq`: 0-based split index within its parent OSM way
  (NULL for manually-created segments, which have no parent way at all).
- The old single-column `osm_way_id` unique constraint is replaced with a
  composite `(osm_way_id, way_seq)` unique constraint - the actual stable,
  deterministic identity of a canonical segment derived from OSM. NULLs in
  either column are still permissive for manually-created rows (Postgres
  unique constraints don't conflict on NULL), so this is a pure widening,
  not a behavior change for non-OSM data.
- `road_segments.access`, `.maxspeed_kph`, `.lanes`: informational columns
  for OSM `access`/`maxspeed`/`lanes` tags (doc TASK202_DESIGN.md §3) -
  captured because the ingestion feature policy explicitly retains them,
  not used by any routing/filtering logic yet.
- `roads`: adds a `(source, name)` unique constraint, needed for
  idempotent Road upserts when grouping same-named OSM ways (also
  NULL-permissive, so unnamed roads are unaffected).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("road_segments", sa.Column("way_seq", sa.Integer(), nullable=True))
    op.add_column("road_segments", sa.Column("access", sa.Text(), nullable=True))
    op.add_column("road_segments", sa.Column("maxspeed_kph", sa.Integer(), nullable=True))
    op.add_column("road_segments", sa.Column("lanes", sa.Integer(), nullable=True))

    op.drop_constraint("uq_road_segments_osm_way_id", "road_segments", type_="unique")
    op.create_unique_constraint(
        "uq_road_segments_osm_way_id_way_seq",
        "road_segments",
        ["osm_way_id", "way_seq"],
    )

    op.create_unique_constraint("uq_roads_source_name", "roads", ["source", "name"])


def downgrade() -> None:
    op.drop_constraint("uq_roads_source_name", "roads", type_="unique")

    op.drop_constraint("uq_road_segments_osm_way_id_way_seq", "road_segments", type_="unique")
    op.create_unique_constraint("uq_road_segments_osm_way_id", "road_segments", ["osm_way_id"])

    op.drop_column("road_segments", "lanes")
    op.drop_column("road_segments", "maxspeed_kph")
    op.drop_column("road_segments", "access")
    op.drop_column("road_segments", "way_seq")
