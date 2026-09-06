"""Sanity check that the database the test suite runs against is actually
at the expected Alembic head - CI runs `alembic upgrade head` before
pytest (see .github/workflows/ci.yml), so this catches a skipped/failed
migration step rather than every other test failing with confusing
"table does not exist" errors."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def test_database_is_at_expected_alembic_head(db_session: AsyncSession) -> None:
    result = await db_session.execute(text("SELECT version_num FROM alembic_version"))
    version = result.scalar_one()

    assert version == "0002", (
        f"expected the transportation-foundation migration (0002) to be applied, "
        f"got {version!r} - run `alembic upgrade head` from services/api"
    )
