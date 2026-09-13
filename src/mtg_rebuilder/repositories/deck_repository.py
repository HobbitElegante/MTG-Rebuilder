from collections.abc import Iterable

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from mtg_rebuilder.models import Card, CardAssignment, CardCopy, Deck, DeckCard
from mtg_rebuilder.models.enums import DeckCardRole, DeckStatus


class DeckRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_decks(self, status: DeckStatus | None = None) -> list[Deck]:
        query = select(Deck).order_by(Deck.sort_order, Deck.name, Deck.id)
        if status is not None:
            query = query.where(Deck.status == status)
        return list(self._session.scalars(query).all())

    def get(self, deck_id: int) -> Deck | None:
        return self._session.get(Deck, deck_id)

    def max_sort_order(self) -> int | None:
        current = self._session.scalar(select(func.max(Deck.sort_order)))
        return None if current is None else int(current)

    def add(self, deck: Deck) -> Deck:
        self._session.add(deck)
        self._session.flush()
        return deck

    def delete(self, deck: Deck) -> None:
        self._session.delete(deck)
        self._session.flush()

    def count_all(self) -> int:
        return int(self._session.scalar(select(func.count()).select_from(Deck)) or 0)

    def count_armed(self) -> int:
        return int(
            self._session.scalar(
                select(func.count())
                .select_from(Deck)
                .where(Deck.status == DeckStatus.ARMED)
            )
            or 0
        )

    def count_deck_cards(self) -> int:
        return int(
            self._session.scalar(select(func.count()).select_from(DeckCard)) or 0
        )

    def list_armed(
        self,
        *,
        exclude_deck_id: int | None = None,
        include_locked: bool = True,
    ) -> list[Deck]:
        query = select(Deck).where(Deck.status == DeckStatus.ARMED)
        if exclude_deck_id is not None:
            query = query.where(Deck.id != exclude_deck_id)
        if not include_locked:
            query = query.where(Deck.is_locked.is_(False))
        return list(self._session.scalars(query).all())

    def role_card_name(self, deck_id: int, role: DeckCardRole) -> str | None:
        row = self._session.execute(
            select(Card.name)
            .join(DeckCard, DeckCard.card_id == Card.oracle_id)
            .where(
                DeckCard.deck_id == deck_id,
                DeckCard.role == role,
            )
            .order_by(Card.name)
            .limit(1)
        ).first()
        return row[0] if row else None

    def command_zone_rows(
        self, deck_id: int
    ) -> list[tuple[DeckCardRole, str, str]]:
        priority = {
            DeckCardRole.COMMANDER,
            DeckCardRole.PARTNER,
            DeckCardRole.COMPANION,
            DeckCardRole.BACKGROUND,
        }
        rows = self._session.execute(
            select(DeckCard.role, Card.oracle_id, Card.name)
            .join(Card, Card.oracle_id == DeckCard.card_id)
            .where(
                DeckCard.deck_id == deck_id,
                DeckCard.role.in_(tuple(priority)),
            )
        ).all()
        return [(role, oracle_id, name) for role, oracle_id, name in rows]

    def secondary_command_zone_rows(
        self, deck_id: int
    ) -> list[tuple[DeckCardRole, str]]:
        rows = self._session.execute(
            select(DeckCard.role, Card.name)
            .join(Card, Card.oracle_id == DeckCard.card_id)
            .where(
                DeckCard.deck_id == deck_id,
                DeckCard.role.in_(
                    (
                        DeckCardRole.PARTNER,
                        DeckCardRole.COMPANION,
                        DeckCardRole.BACKGROUND,
                    )
                ),
            )
        ).all()
        return [(role, name) for role, name in rows]

    def list_deck_cards_by_role(
        self, deck_id: int, role: DeckCardRole
    ) -> list[DeckCard]:
        return list(
            self._session.scalars(
                select(DeckCard).where(
                    DeckCard.deck_id == deck_id,
                    DeckCard.role == role,
                )
            ).all()
        )

    def get_deck_card(
        self, deck_id: int, card_id: str, role: DeckCardRole
    ) -> DeckCard | None:
        return self._session.scalar(
            select(DeckCard).where(
                DeckCard.deck_id == deck_id,
                DeckCard.card_id == card_id,
                DeckCard.role == role,
            )
        )

    def add_deck_card(self, deck_card: DeckCard) -> DeckCard:
        self._session.add(deck_card)
        return deck_card

    def delete_deck_card(self, deck_card: DeckCard) -> None:
        self._session.delete(deck_card)

    def delete_deck_cards(self, deck_id: int) -> None:
        self._session.execute(delete(DeckCard).where(DeckCard.deck_id == deck_id))
        self._session.flush()

    def delete_assignments_for_deck(self, deck_id: int) -> None:
        self._session.execute(
            delete(CardAssignment).where(CardAssignment.deck_id == deck_id)
        )
        self._session.flush()

    def list_deck_cards_with_card(
        self,
        deck_id: int,
        *,
        exclude_token: bool = False,
        order_by_name: bool = True,
    ) -> list[tuple[DeckCard, Card]]:
        query = (
            select(DeckCard, Card)
            .join(Card, Card.oracle_id == DeckCard.card_id)
            .where(DeckCard.deck_id == deck_id)
        )
        if exclude_token:
            query = query.where(DeckCard.role != DeckCardRole.TOKEN)
        if order_by_name:
            query = query.order_by(Card.name, DeckCard.role)
        return list(self._session.execute(query).all())

    def list_export_cards(self, deck_id: int) -> list[tuple[DeckCard, Card]]:
        return list(
            self._session.execute(
                select(DeckCard, Card)
                .join(Card, Card.oracle_id == DeckCard.card_id)
                .where(DeckCard.deck_id == deck_id)
                .order_by(DeckCard.role, Card.name)
            ).all()
        )

    def requirements(self, deck_id: int) -> dict[str, int]:
        rows = self._session.execute(
            select(DeckCard.card_id, func.sum(DeckCard.quantity))
            .join(Card, Card.oracle_id == DeckCard.card_id)
            .where(
                DeckCard.deck_id == deck_id,
                DeckCard.role != DeckCardRole.TOKEN,
                Card.is_basic_land.is_(False),
                Card.is_token.is_(False),
            )
            .group_by(DeckCard.card_id)
        ).all()
        return {card_id: int(qty) for card_id, qty in rows}

    def basic_land_requirements(self, deck_id: int) -> dict[str, int]:
        rows = self._session.execute(
            select(DeckCard.card_id, func.sum(DeckCard.quantity))
            .join(Card, Card.oracle_id == DeckCard.card_id)
            .where(
                DeckCard.deck_id == deck_id,
                DeckCard.role != DeckCardRole.TOKEN,
                Card.is_basic_land.is_(True),
            )
            .group_by(DeckCard.card_id)
        ).all()
        return {card_id: int(qty) for card_id, qty in rows}

    def commander_legality_rows(
        self, deck_id: int
    ) -> list[tuple[str, str, str | None]]:
        rows = self._session.execute(
            select(Card.oracle_id, Card.name, Card.commander_legality)
            .join(DeckCard, DeckCard.card_id == Card.oracle_id)
            .where(
                DeckCard.deck_id == deck_id,
                DeckCard.role != DeckCardRole.TOKEN,
            )
            .distinct()
        ).all()
        return [(oracle_id, name, legality) for oracle_id, name, legality in rows]

    def commander_rule_rows(
        self, deck_id: int
    ) -> list[tuple[str, str, str, int, str | None, str | None, str | None, bool]]:
        """Fields needed for Commander game-rule checks.

        Includes basics (they count toward deck size) and per-row quantity.
        Color-identity / singleton logic skips basics in :func:`evaluate_deck`.
        """
        rows = self._session.execute(
            select(
                Card.oracle_id,
                Card.name,
                DeckCard.role,
                DeckCard.quantity,
                Card.color_identity,
                Card.oracle_text,
                Card.type_line,
                Card.is_basic_land,
            )
            .join(DeckCard, DeckCard.card_id == Card.oracle_id)
            .where(
                DeckCard.deck_id == deck_id,
                DeckCard.role != DeckCardRole.TOKEN,
            )
        ).all()
        return [
            (
                oracle_id,
                name,
                str(role),
                int(quantity),
                color_identity,
                oracle_text,
                type_line,
                bool(is_basic_land),
            )
            for (
                oracle_id,
                name,
                role,
                quantity,
                color_identity,
                oracle_text,
                type_line,
                is_basic_land,
            ) in rows
        ]

    def deck_names_for_card(self, oracle_id: str) -> tuple[str, ...]:
        return tuple(
            self._session.scalars(
                select(Deck.name)
                .join(CardAssignment, CardAssignment.deck_id == Deck.id)
                .join(CardCopy, CardCopy.id == CardAssignment.card_copy_id)
                .where(CardCopy.card_id == oracle_id)
                .distinct()
                .order_by(Deck.name)
            ).all()
        )

    def deck_ids_for_card(self, oracle_id: str) -> frozenset[int]:
        return frozenset(
            self._session.scalars(
                select(Deck.id)
                .join(CardAssignment, CardAssignment.deck_id == Deck.id)
                .join(CardCopy, CardCopy.id == CardAssignment.card_copy_id)
                .where(CardCopy.card_id == oracle_id)
                .distinct()
            ).all()
        )

    def assignment_decks_by_card(
        self,
    ) -> dict[str, tuple[tuple[int, str], ...]]:
        """Deck id/name holding each card, grouped by oracle id (one query).

        Deck names within each card are ordered alphabetically (same as
        ``deck_names_for_card``).
        """
        rows = self._session.execute(
            select(CardCopy.card_id, Deck.id, Deck.name)
            .join(CardAssignment, CardAssignment.card_copy_id == CardCopy.id)
            .join(Deck, Deck.id == CardAssignment.deck_id)
            .distinct()
            .order_by(CardCopy.card_id, Deck.name)
        ).all()
        grouped: dict[str, list[tuple[int, str]]] = {}
        for card_id, deck_id, deck_name in rows:
            grouped.setdefault(card_id, []).append((int(deck_id), deck_name))
        return {
            card_id: tuple(entries) for card_id, entries in grouped.items()
        }

    def commander_names_by_deck(self) -> dict[int, str]:
        """Commander display name for every deck that has one (one query)."""
        rows = self._session.execute(
            select(DeckCard.deck_id, Card.name)
            .join(Card, Card.oracle_id == DeckCard.card_id)
            .where(DeckCard.role == DeckCardRole.COMMANDER)
            .order_by(DeckCard.deck_id, Card.name)
        ).all()
        names: dict[int, str] = {}
        for deck_id, name in rows:
            # First name wins if a deck somehow has multiple COMMANDER rows.
            names.setdefault(int(deck_id), name)
        return names

    def inventory_copy_rows(
        self,
    ) -> list[
        tuple[
            str,
            str,
            str | None,
            int,
            str | None,
            str | None,
            float | None,
            str | None,
            str | None,
            str | None,
            str | None,
            bool,
            bool,
        ]
    ]:
        rows = self._session.execute(
            select(
                Card.oracle_id,
                Card.name,
                Card.color_identity,
                func.count(CardCopy.id),
                Card.type_line,
                Card.colors,
                Card.cmc,
                Card.mana_cost,
                Card.rarity,
                Card.oracle_text,
                Card.commander_legality,
                Card.is_basic_land,
                Card.is_token,
            )
            .join(Card, Card.oracle_id == CardCopy.card_id)
            .group_by(
                Card.oracle_id,
                Card.name,
                Card.color_identity,
                Card.type_line,
                Card.colors,
                Card.cmc,
                Card.mana_cost,
                Card.rarity,
                Card.oracle_text,
                Card.commander_legality,
                Card.is_basic_land,
                Card.is_token,
            )
            .order_by(Card.name)
        ).all()
        return [
            (
                oracle_id,
                name,
                color_identity,
                int(total),
                type_line,
                colors,
                cmc,
                mana_cost,
                rarity,
                oracle_text,
                commander_legality,
                bool(is_basic_land),
                bool(is_token),
            )
            for (
                oracle_id,
                name,
                color_identity,
                total,
                type_line,
                colors,
                cmc,
                mana_cost,
                rarity,
                oracle_text,
                commander_legality,
                is_basic_land,
                is_token,
            ) in rows
        ]

    def distinct_card_ids(self) -> set[str]:
        return set(self._session.scalars(select(DeckCard.card_id).distinct()).all())

    def flush(self) -> None:
        self._session.flush()
