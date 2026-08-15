"""Add deck format tag (Commander default; other formats hook later).

Revision ID: 006_deck_format
Revises: 005_card_rarity
Create Date: 2026-08-11

``decks.format`` stores the game-format tag used to pick advisory rule
profiles. Existing rows backfill to COMMANDER via server_default.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006_deck_format"
down_revision: Union[str, Sequence[str], None] = "005_card_rarity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("decks") as batch:
        batch.add_column(
            sa.Column(
                "format",
                sa.String(length=32),
                nullable=False,
                server_default="COMMANDER",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("decks") as batch:
        batch.drop_column("format")
