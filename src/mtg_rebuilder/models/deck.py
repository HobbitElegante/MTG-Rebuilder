from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mtg_rebuilder.models.base import Base
from mtg_rebuilder.models.enums import DeckCardRole, DeckFormat, DeckStatus


class Deck(Base):
    __tablename__ = "decks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[DeckStatus] = mapped_column(
        Enum(DeckStatus, native_enum=False),
        default=DeckStatus.DISMANTLED,
        nullable=False,
    )
    format: Mapped[DeckFormat] = mapped_column(
        Enum(DeckFormat, native_enum=False),
        default=DeckFormat.COMMANDER,
        nullable=False,
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    cards: Mapped[list["DeckCard"]] = relationship(
        back_populates="deck",
        cascade="all, delete-orphan",
    )
    assignments: Mapped[list["CardAssignment"]] = relationship(
        back_populates="deck",
        cascade="all, delete-orphan",
    )


class DeckCard(Base):
    __tablename__ = "deck_cards"
    __table_args__ = (
        UniqueConstraint("deck_id", "card_id", "role", name="uq_deck_card_role"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    deck_id: Mapped[int] = mapped_column(ForeignKey("decks.id"), nullable=False)
    card_id: Mapped[str] = mapped_column(ForeignKey("cards.oracle_id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    role: Mapped[DeckCardRole] = mapped_column(
        Enum(DeckCardRole, native_enum=False),
        default=DeckCardRole.MAIN,
        nullable=False,
    )

    deck: Mapped["Deck"] = relationship(back_populates="cards")
    card: Mapped["Card"] = relationship()


class CardAssignment(Base):
    __tablename__ = "card_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    card_copy_id: Mapped[int] = mapped_column(
        ForeignKey("card_copies.id"),
        unique=True,
        nullable=False,
    )
    deck_id: Mapped[int] = mapped_column(ForeignKey("decks.id"), nullable=False)

    card_copy: Mapped["CardCopy"] = relationship(back_populates="assignment")
    deck: Mapped["Deck"] = relationship(back_populates="assignments")


from mtg_rebuilder.models.card import Card, CardCopy  # noqa: E402
