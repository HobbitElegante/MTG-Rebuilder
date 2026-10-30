from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mtg_rebuilder.models.base import Base


class Card(Base):
    __tablename__ = "cards"

    oracle_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    mana_cost: Mapped[str | None] = mapped_column(String(64))
    type_line: Mapped[str | None] = mapped_column(String(255))
    oracle_text: Mapped[str | None] = mapped_column(Text)
    colors: Mapped[str | None] = mapped_column(String(16))
    color_identity: Mapped[str | None] = mapped_column(String(16))
    cmc: Mapped[float | None] = mapped_column()
    # Scryfall rarity of the representative print (bulk / lookup). Print-level
    # rarities for tracked editions live on CardPrint.
    rarity: Mapped[str | None] = mapped_column(String(16))
    image_uri: Mapped[str | None] = mapped_column(String(512))
    # Back face of double-faced cards; None for single-faced cards.
    image_uri_back: Mapped[str | None] = mapped_column(String(512))
    # Scryfall legalities.commander: legal | not_legal | banned | restricted
    commander_legality: Mapped[str | None] = mapped_column(String(16))
    is_basic_land: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_token: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    copies: Mapped[list["CardCopy"]] = relationship(back_populates="card")


class CardPrint(Base):
    """A set the card was printed in, cached for the edition picker.

    The oracle bulk pack collapses to one row per card, so the sets a card
    exists in are fetched per card on demand and kept here.
    """

    __tablename__ = "card_prints"
    __table_args__ = (
        UniqueConstraint("oracle_id", "set_code", name="uq_card_print_set"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    oracle_id: Mapped[str] = mapped_column(
        ForeignKey("cards.oracle_id"), index=True, nullable=False
    )
    set_code: Mapped[str] = mapped_column(String(16), nullable=False)
    set_name: Mapped[str | None] = mapped_column(String(255))
    released_at: Mapped[str | None] = mapped_column(String(16))
    # Scryfall rarity for this set (common / uncommon / rare / mythic / …).
    rarity: Mapped[str | None] = mapped_column(String(16))


class CardPrinting(Base):
    """One Scryfall printing, cached for the art combo.

    Unlike ``CardPrint`` this is not collapsed to a set: two collector numbers
    in the same set are two rows. ``id`` is the Scryfall card id. No index on
    ``oracle_id`` until a real filter's EXPLAIN shows a scan worth indexing.
    """

    __tablename__ = "card_printings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    oracle_id: Mapped[str] = mapped_column(
        ForeignKey("cards.oracle_id"), nullable=False
    )
    set_code: Mapped[str] = mapped_column(String(16), nullable=False)
    collector_number: Mapped[str | None] = mapped_column(String(32))
    illustration_id: Mapped[str | None] = mapped_column(String(36))
    label: Mapped[str | None] = mapped_column(String(255))
    # Scryfall ``small`` image, for the print grid. Empty when the printing
    # was fetched and has no image. NULL means this row predates that lookup.
    image_uri: Mapped[str | None] = mapped_column(String(512))


class CardCopy(Base):
    __tablename__ = "card_copies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    card_id: Mapped[str] = mapped_column(
        ForeignKey("cards.oracle_id"), index=True, nullable=False
    )
    edition: Mapped[str | None] = mapped_column(String(16))
    language: Mapped[str | None] = mapped_column(String(8))
    # Legacy NOT NULL flag. The app reads and writes ``finish`` instead:
    # false was the column default, not a recorded nonfoil.
    foil: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # nonfoil / foil / etched / glossy, or NULL when the user has not said.
    finish: Mapped[str | None] = mapped_column(String(16))
    condition: Mapped[str | None] = mapped_column(String(32))
    collector_number: Mapped[str | None] = mapped_column(String(32))
    # Scryfall card id of this printing (set + number + art). Not a FK:
    # the catalog row is optional and fetched on demand.
    printing_id: Mapped[str | None] = mapped_column(String(36))
    # Touched when a print fact changes, so the preview can follow the copy
    # the user edited last. NULL on rows that have not been edited since.
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    location: Mapped[str | None] = mapped_column(String(128))

    card: Mapped["Card"] = relationship(back_populates="copies")
    assignment: Mapped["CardAssignment | None"] = relationship(
        back_populates="card_copy",
        uselist=False,
    )


from mtg_rebuilder.models.deck import CardAssignment  # noqa: E402
