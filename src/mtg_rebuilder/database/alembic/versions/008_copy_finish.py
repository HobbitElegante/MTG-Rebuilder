"""Record a finish separately from the legacy foil flag.

Revision ID: 008_copy_finish
Revises: 007_lookup_indexes
Create Date: 2026-10-29

``card_copies.foil`` is NOT NULL and defaulted to false, so "not foil" and
"never recorded" were the same value, and etched or glossy did not fit.
``finish`` is nullable: NULL means unspecified. Existing true flags become
``foil``; the default false stays NULL because nobody set it in the UI.
The ``foil`` column is left in place.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008_copy_finish"
down_revision: Union[str, Sequence[str], None] = "007_lookup_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "card_copies",
        sa.Column("finish", sa.String(length=16), nullable=True),
    )
    op.execute("UPDATE card_copies SET finish = 'foil' WHERE foil = 1")


def downgrade() -> None:
    op.drop_column("card_copies", "finish")
