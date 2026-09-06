"""Shared SQLAlchemy declarative base.

Deliberately empty of models in Phase 1 - see
docs/architecture/12-development-phases.md Phase 1 ("do not prematurely
implement all domain tables"). Domain models (docs/architecture/04) land in
Phase 2+; Alembic's migration environment already points at this metadata
object so adding a model later is a matter of importing it here, not
rewiring migrations.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
