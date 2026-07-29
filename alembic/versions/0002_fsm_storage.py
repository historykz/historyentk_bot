"""add fsm_storage table

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-29

Adds the fsm_storage table (backing PostgresStorage) so FSM state can persist
without Redis. Uses the same create_all-from-models approach as 0001 — safe to
run repeatedly, only creates tables that don't already exist.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

from app.db.base import Base
from app.db import models  # noqa: F401

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    models.FsmStorageEntry.__table__.drop(bind=bind, checkfirst=True)
