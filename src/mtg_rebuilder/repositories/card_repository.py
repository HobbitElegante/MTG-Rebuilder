from collections.abc import Iterable

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from mtg_rebuilder.models import Card, CardCopy
from mtg_rebuilder.models.deck import DeckCard


class CardRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def playable_clause():
        return or_(Card.type_line.is_(None), Card.type_line != "Card // Card")

    def get(self, oracle_id: str) -> Card | None:
        return self._session.get(Card, oracle_id)

    def add(self, card: Card) -> Card:
        self._session.add(card)
        return card

    def flush(self) -> None:
        self._session.flush()

    def count_all(self) -> int:
        return int(self._session.scalar(select(func.count()).select_from(Card)) or 0)

    def count_playable(self) -> int:
        return int(
            self._session.scalar(
                select(func.count())
                .select_from(Card)
                .where(self.playable_clause())
            )
            or 0
        )

    def list_all(self) -> list[Card]:
        return list(self._session.scalars(select(Card)).all())

    def list_playable(self, search: str = "") -> list[Card]:
        query = select(Card).where(self.playable_clause()).order_by(Card.name)
        trimmed = search.strip()
        if trimmed:
            query = query.where(Card.name.ilike(f"%{trimmed}%"))
        return list(self._session.scalars(query).all())

    def list_by_oracle_ids(self, oracle_ids: Iterable[str]) -> list[Card]:
        ids = list(oracle_ids)
        if not ids:
            return []
        return list(
            self._session.scalars(select(Card).where(Card.oracle_id.in_(ids))).all()
        )

    def names_by_ids(self, oracle_ids: Iterable[str]) -> dict[str, str]:
        return {card.oracle_id: card.name for card in self.list_by_oracle_ids(oracle_ids)}

    def list_exact_lower(self, name: str) -> list[Card]:
        return list(
            self._session.scalars(
                select(Card).where(func.lower(Card.name) == name.casefold())
            ).all()
        )

    def list_fuzzy(self, name: str, *, limit: int = 20) -> list[Card]:
        return list(
            self._session.scalars(
                select(Card).where(Card.name.ilike(f"%{name}%")).limit(limit)
            ).all()
        )

    def list_with_image_uri(self, *, ordered: bool = False) -> list[Card]:
        query = select(Card).where(Card.image_uri.is_not(None))
        if ordered:
            query = query.order_by(Card.name)
        return list(self._session.scalars(query).all())

    def oracle_ids_with_image_uri(self) -> set[str]:
        return set(
            self._session.scalars(
                select(Card.oracle_id).where(Card.image_uri.is_not(None))
            ).all()
        )

    def collection_oracle_ids(self) -> list[str]:
        copy_ids = set(self._session.scalars(select(CardCopy.card_id).distinct()).all())
        deck_ids = set(self._session.scalars(select(DeckCard.card_id).distinct()).all())
        return sorted(copy_ids | deck_ids)

    def purge_orphan_art_series(self) -> int:
        referenced = (
            select(CardCopy.card_id).union(select(DeckCard.card_id))
        ).subquery()
        result = self._session.execute(
            delete(Card).where(
                Card.type_line == "Card // Card",
                Card.oracle_id.not_in(select(referenced.c.card_id)),
            )
        )
        self._session.flush()
        return int(result.rowcount or 0)
