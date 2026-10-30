"""Index the foreign keys SQLite leaves unindexed, plus deck status and order.

Revision ID: 007_lookup_indexes
Revises: 006_deck_format
Create Date: 2026-10-29

Lookups by card (``card_copies.card_id``, ``deck_cards.card_id``) and by deck
(``card_assignments.deck_id``, ``decks.status``, ``decks.sort_order``) were full
scans. ``deck_cards.deck_id`` is already the leading column of
``uq_deck_card_role``, so it needs no index of its own.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "007_lookup_indexes"
down_revision: Union[str, Sequence[str], None] = "006_deck_format"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEXES = (
    ("ix_card_copies_card_id", "card_copies", ["card_id"]),
    ("ix_deck_cards_card_id", "deck_cards", ["card_id"]),
    ("ix_card_assignments_deck_id", "card_assignments", ["deck_id"]),
    ("ix_decks_status", "decks", ["status"]),
    ("ix_decks_sort_order", "decks", ["sort_order"]),
)


def upgrade() -> None:
    for name, table, columns in _INDEXES:
        op.create_index(name, table, columns, unique=False)


def downgrade() -> None:
    for name, table, _columns in reversed(_INDEXES):
        op.drop_index(name, table_name=table)
