"""enable postgis extension

Revision ID: 0001
Revises:
Create Date: 2026-09-06

Establishes the spatial foundation the approved data model
(docs/architecture/04-data-model.md) depends on for every geometry column
added from Phase 2 onward. Deliberately the only thing this migration does
- Phase 1 does not create domain tables yet
(docs/architecture/12-development-phases.md Phase 1).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS postgis")
