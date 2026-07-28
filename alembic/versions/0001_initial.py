"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-07-29

This initial migration builds the schema directly from the SQLAlchemy models
(`Base.metadata`), which guarantees it never drifts from app/db/models.py.
Any schema change after this point should be added as a new migration via
`alembic revision --autogenerate -m "..."` (see README "Working with migrations").
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

from app.db.base import Base
from app.db import models  # noqa: F401

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
