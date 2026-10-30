"""Collector number on the physical copy.

Revision ID: 009_copy_collector
Revises: 008_copy_finish
Create Date: 2026-10-29

``card_prints`` is one row per set, so two arts in the same set cannot live
there. The number belongs on the copy and may stay empty.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009_copy_collector"
down_revision: Union[str, Sequence[str], None] = "008_copy_finish"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "card_copies",
        sa.Column("collector_number", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("card_copies", "collector_number")
