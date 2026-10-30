"""When a physical copy's print facts last changed.

Revision ID: 012_copy_updated_at
Revises: 011_printing_image
Create Date: 2026-10-29

The card preview follows the copy that was updated last among those with a
printing. Existing rows stay NULL until the next edit. No extra index.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012_copy_updated_at"
down_revision: Union[str, Sequence[str], None] = "011_printing_image"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "card_copies",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("card_copies", "updated_at")
