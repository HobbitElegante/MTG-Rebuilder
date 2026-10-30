"""Image URL on each cached Scryfall printing.

Revision ID: 011_printing_image
Revises: 010_card_printings
Create Date: 2026-10-29

The print grid shows the art. The URL is filled the next time that card's
printings are fetched. No extra index.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011_printing_image"
down_revision: Union[str, Sequence[str], None] = "010_card_printings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "card_printings",
        sa.Column("image_uri", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("card_printings", "image_uri")
