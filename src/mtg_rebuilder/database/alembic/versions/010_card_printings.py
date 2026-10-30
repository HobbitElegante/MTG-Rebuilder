"""Scryfall printing id on the copy, and a per-printing catalog.

Revision ID: 010_card_printings
Revises: 009_copy_collector
Create Date: 2026-10-29

``card_prints`` stays one row per set (edition combo and rarity). ``card_printings``
is one row per Scryfall card id, fetched when the art combo opens. No extra
index: lookups are by the card the user is editing, and foil/set/art are not
filtered yet.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010_card_printings"
down_revision: Union[str, Sequence[str], None] = "009_copy_collector"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "card_copies",
        sa.Column("printing_id", sa.String(length=36), nullable=True),
    )
    op.create_table(
        "card_printings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("oracle_id", sa.String(length=36), nullable=False),
        sa.Column("set_code", sa.String(length=16), nullable=False),
        sa.Column("collector_number", sa.String(length=32), nullable=True),
        sa.Column("illustration_id", sa.String(length=36), nullable=True),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["oracle_id"], ["cards.oracle_id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("card_printings")
    op.drop_column("card_copies", "printing_id")
