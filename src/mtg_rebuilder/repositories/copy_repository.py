from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from mtg_rebuilder.algorithms.copy_traits import preferred_printing_id
from mtg_rebuilder.models import Card, CardAssignment, CardCopy, Deck

# Fields the app records on a copy. ``foil`` is not one of them.
_TRAIT_FIELDS = (
    "edition",
    "finish",
    "language",
    "condition",
    "collector_number",
    "printing_id",
)


@dataclass(frozen=True)
class CopyTraitCounts:
    """Grouped values per card. ``None`` keys are copies with that field empty."""

    finishes: dict[str, dict[str | None, int]]
    languages: dict[str, dict[str | None, int]]
    conditions: dict[str, dict[str | None, int]]
    collector_numbers: dict[str, dict[str | None, int]]


class CopyRepository:
    """Physical card-copy persistence (free vs assigned inventory)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _assigned_copy_ids():
        return select(CardAssignment.card_copy_id)

    def add(self, card_id: str) -> CardCopy:
        copy = CardCopy(card_id=card_id)
        self._session.add(copy)
        return copy

    def add_many(
        self,
        card_id: str,
        quantity: int,
        *,
        edition: str | None = None,
        finish: str | None = None,
        language: str | None = None,
        condition: str | None = None,
        collector_number: str | None = None,
        printing_id: str | None = None,
    ) -> list[CardCopy]:
        stamped = datetime.now(timezone.utc) if printing_id else None
        copies = [
            CardCopy(
                card_id=card_id,
                edition=edition,
                finish=finish,
                language=language,
                condition=condition,
                collector_number=collector_number,
                printing_id=printing_id,
                updated_at=stamped,
            )
            for _ in range(quantity)
        ]
        for copy in copies:
            self._session.add(copy)
        self._session.flush()
        return copies

    def delete_copies(self, copies: Iterable[CardCopy]) -> None:
        for copy in copies:
            self._session.delete(copy)
        self._session.flush()

    def count_total(self, oracle_id: str) -> int:
        return int(
            self._session.scalar(
                select(func.count())
                .select_from(CardCopy)
                .where(CardCopy.card_id == oracle_id)
            )
            or 0
        )

    def count_assigned(self, oracle_id: str) -> int:
        return int(
            self._session.scalar(
                select(func.count())
                .select_from(CardCopy)
                .join(CardAssignment, CardAssignment.card_copy_id == CardCopy.id)
                .where(CardCopy.card_id == oracle_id)
            )
            or 0
        )

    def assigned_counts(self) -> dict[str, int]:
        """Assigned copy counts grouped by oracle id (one query)."""
        rows = self._session.execute(
            select(CardCopy.card_id, func.count(CardCopy.id))
            .join(CardAssignment, CardAssignment.card_copy_id == CardCopy.id)
            .group_by(CardCopy.card_id)
        ).all()
        return {card_id: int(count) for card_id, count in rows}

    def count_all(self) -> int:
        return int(
            self._session.scalar(select(func.count()).select_from(CardCopy)) or 0
        )

    def count_unassigned(self) -> int:
        return int(
            self._session.scalar(
                select(func.count())
                .select_from(CardCopy)
                .where(CardCopy.id.not_in(self._assigned_copy_ids()))
            )
            or 0
        )

    def count_assignments(self) -> int:
        return int(
            self._session.scalar(select(func.count()).select_from(CardAssignment))
            or 0
        )

    def free_counts(self) -> dict[str, int]:
        rows = self._session.execute(
            select(CardCopy.card_id, func.count(CardCopy.id))
            .where(CardCopy.id.not_in(self._assigned_copy_ids()))
            .group_by(CardCopy.card_id)
        ).all()
        return {card_id: count for card_id, count in rows}

    def counts_by_card(self) -> dict[str, int]:
        rows = self._session.execute(
            select(CardCopy.card_id, func.count(CardCopy.id)).group_by(CardCopy.card_id)
        ).all()
        return {card_id: count for card_id, count in rows}

    def totals_for_cards(self, oracle_ids: Iterable[str]) -> dict[str, int]:
        ids = list(oracle_ids)
        if not ids:
            return {}
        rows = self._session.execute(
            select(CardCopy.card_id, func.count(CardCopy.id))
            .where(CardCopy.card_id.in_(ids))
            .group_by(CardCopy.card_id)
        ).all()
        return {card_id: int(count) for card_id, count in rows}

    def free_counts_for(self, oracle_ids: Iterable[str]) -> dict[str, int]:
        """Unassigned copy counts for the given oracle ids (one query)."""
        ids = list(oracle_ids)
        if not ids:
            return {}
        rows = self._session.execute(
            select(CardCopy.card_id, func.count(CardCopy.id))
            .where(
                CardCopy.card_id.in_(ids),
                CardCopy.id.not_in(self._assigned_copy_ids()),
            )
            .group_by(CardCopy.card_id)
        ).all()
        return {card_id: int(count) for card_id, count in rows}

    def list_free(self, oracle_id: str, *, limit: int | None = None) -> list[CardCopy]:
        query = (
            select(CardCopy)
            .where(
                CardCopy.card_id == oracle_id,
                CardCopy.id.not_in(self._assigned_copy_ids()),
            )
            .order_by(CardCopy.id)
        )
        if limit is not None:
            query = query.limit(limit)
        return list(self._session.scalars(query).all())

    def list_all_unassigned(self) -> list[CardCopy]:
        return list(
            self._session.scalars(
                select(CardCopy)
                .where(CardCopy.id.not_in(self._assigned_copy_ids()))
                .order_by(CardCopy.id)
            ).all()
        )

    def list_assigned_to_deck(
        self,
        deck_id: int,
        oracle_id: str,
        *,
        limit: int | None = None,
    ) -> list[CardCopy]:
        query = (
            select(CardCopy)
            .join(CardAssignment, CardAssignment.card_copy_id == CardCopy.id)
            .where(
                CardAssignment.deck_id == deck_id,
                CardCopy.card_id == oracle_id,
            )
            .order_by(CardCopy.id)
        )
        if limit is not None:
            query = query.limit(limit)
        return list(self._session.scalars(query).all())

    def assigned_counts_for_deck(
        self, deck_id: int, oracle_ids: Iterable[str]
    ) -> dict[str, int]:
        ids = list(oracle_ids)
        if not ids:
            return {}
        rows = self._session.execute(
            select(CardCopy.card_id, func.count(CardCopy.id))
            .join(CardAssignment, CardAssignment.card_copy_id == CardCopy.id)
            .where(
                CardAssignment.deck_id == deck_id,
                CardCopy.card_id.in_(ids),
            )
            .group_by(CardCopy.card_id)
        ).all()
        return {card_id: count for card_id, count in rows}

    def delete_assignment_for_copy(self, card_copy_id: int) -> None:
        self._session.execute(
            delete(CardAssignment).where(CardAssignment.card_copy_id == card_copy_id)
        )

    def add_assignment(self, card_copy_id: int, deck_id: int) -> CardAssignment:
        assignment = CardAssignment(card_copy_id=card_copy_id, deck_id=deck_id)
        self._session.add(assignment)
        return assignment

    def edition_counts(self) -> dict[str, dict[str | None, int]]:
        """Copies per (card, edition); ``None`` keys are unspecified editions."""
        rows = self._session.execute(
            select(CardCopy.card_id, CardCopy.edition, func.count(CardCopy.id))
            .group_by(CardCopy.card_id, CardCopy.edition)
        ).all()
        counts: dict[str, dict[str | None, int]] = {}
        for card_id, edition, count in rows:
            counts.setdefault(card_id, {})[edition] = int(count)
        return counts

    def list_with_deck(self, oracle_id: str) -> list[tuple[CardCopy, str | None]]:
        """Every copy of a card with the deck holding it, if any."""
        rows = self._session.execute(
            select(CardCopy, Deck.name)
            .outerjoin(CardAssignment, CardAssignment.card_copy_id == CardCopy.id)
            .outerjoin(Deck, Deck.id == CardAssignment.deck_id)
            .where(CardCopy.card_id == oracle_id)
            .order_by(CardCopy.id)
        ).all()
        return [(copy, deck_name) for copy, deck_name in rows]

    def list_unspecified_for_deck(self, deck_id: int) -> list[tuple[CardCopy, str]]:
        """Copies assigned to a deck that have no edition recorded yet."""
        rows = self._session.execute(
            select(CardCopy, Card.name)
            .join(CardAssignment, CardAssignment.card_copy_id == CardCopy.id)
            .join(Card, Card.oracle_id == CardCopy.card_id)
            .where(
                CardAssignment.deck_id == deck_id,
                CardCopy.edition.is_(None),
                Card.is_basic_land.is_(False),
            )
            .order_by(Card.name, CardCopy.id)
        ).all()
        return [(copy, card_name) for copy, card_name in rows]

    def set_editions(self, editions: dict[int, str | None]) -> int:
        """Assign editions by copy id; returns how many rows changed."""
        return self.set_trait_fields(
            {copy_id: {"edition": edition} for copy_id, edition in editions.items()}
        )

    def set_trait_fields(self, updates: dict[int, dict[str, str | None]]) -> int:
        """Write the given fields on each copy. Omitted fields stay as they are.

        Does not touch ``foil``. Returns how many rows changed.
        """
        if not updates:
            return 0
        copies = self._session.scalars(
            select(CardCopy).where(CardCopy.id.in_(list(updates)))
        ).all()
        changed = 0
        for copy in copies:
            fields = updates.get(copy.id)
            if not fields:
                continue
            row_changed = False
            for name, value in fields.items():
                if name not in _TRAIT_FIELDS:
                    raise ValueError(f"Unknown copy field: {name}")
                if getattr(copy, name) == value:
                    continue
                setattr(copy, name, value)
                row_changed = True
            if row_changed:
                copy.updated_at = datetime.now(timezone.utc)
                changed += 1
        self._session.flush()
        return changed

    def latest_printing_ids(
        self, oracle_ids: Iterable[str] | None = None
    ) -> dict[str, str]:
        """Scryfall id of the most recently updated printed copy, per card."""
        query = select(
            CardCopy.card_id,
            CardCopy.printing_id,
            CardCopy.updated_at,
            CardCopy.id,
        ).where(CardCopy.printing_id.is_not(None))
        if oracle_ids is not None:
            ids = list(oracle_ids)
            if not ids:
                return {}
            query = query.where(CardCopy.card_id.in_(ids))
        grouped: dict[str, list[tuple[str | None, datetime | None, int]]] = {}
        for card_id, printing_id, updated_at, copy_id in self._session.execute(query):
            grouped.setdefault(card_id, []).append((printing_id, updated_at, copy_id))
        chosen: dict[str, str] = {}
        for card_id, copies in grouped.items():
            printing_id = preferred_printing_id(copies)
            if printing_id:
                chosen[card_id] = printing_id
        return chosen

    def trait_counts(
        self, oracle_ids: Iterable[str] | None = None
    ) -> CopyTraitCounts:
        """Finish, language, condition, and collector number grouped by card.

        ``oracle_ids`` None scans every copy (inventory). A list limits the
        query to those cards (deck preview). Display only: stock counts do
        not use this.
        """
        ids = list(oracle_ids) if oracle_ids is not None else None
        return CopyTraitCounts(
            finishes=self._value_counts(CardCopy.finish, ids),
            languages=self._value_counts(CardCopy.language, ids),
            conditions=self._value_counts(CardCopy.condition, ids),
            collector_numbers=self._value_counts(CardCopy.collector_number, ids),
        )

    def _value_counts(
        self, column, oracle_ids: list[str] | None
    ) -> dict[str, dict[str | None, int]]:
        if oracle_ids is not None and not oracle_ids:
            return {}
        query = select(CardCopy.card_id, column, func.count(CardCopy.id)).group_by(
            CardCopy.card_id, column
        )
        if oracle_ids is not None:
            query = query.where(CardCopy.card_id.in_(oracle_ids))
        rows = self._session.execute(query).all()
        counts: dict[str, dict[str | None, int]] = {}
        for card_id, value, count in rows:
            counts.setdefault(card_id, {})[value] = int(count)
        return counts

    def distinct_card_ids(self) -> set[str]:
        return set(self._session.scalars(select(CardCopy.card_id).distinct()).all())
