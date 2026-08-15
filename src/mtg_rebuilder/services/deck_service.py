from dataclasses import dataclass

from sqlalchemy.orm import Session

from mtg_rebuilder.algorithms.card_utils import is_scryfall_legality_issue
from mtg_rebuilder.algorithms.commander_rules import (
    CommanderCard,
    CommanderRuleIssue,
)
from mtg_rebuilder.algorithms.deck_stats import (
    DeckStatistics,
    DeckStatsCard,
    compute_deck_statistics,
)
from mtg_rebuilder.algorithms.format_rules import profile_for
from mtg_rebuilder.models import CardCopy, Deck, DeckCard
from mtg_rebuilder.models.enums import (
    ActivityEventType,
    DeckCardRole,
    DeckFormat,
    DeckStatus,
)
from mtg_rebuilder.repositories import CardRepository, CopyRepository, DeckRepository
from mtg_rebuilder.services.activity_service import ActivityService


@dataclass(frozen=True)
class DeckDeleteCardImpact:
    oracle_id: str
    name: str
    list_quantity: int
    total_copies: int
    removable_copies: int

    @property
    def assigned_elsewhere(self) -> int:
        return max(0, self.total_copies - self.removable_copies)


@dataclass(frozen=True)
class DeckEditRow:
    oracle_id: str
    name: str
    quantity: int
    role: DeckCardRole
    free_copies: int
    is_basic_land: bool
    is_token: bool
    removable_copies: int
    commander_legality: str | None = None


@dataclass(frozen=True)
class DeckCardSummary:
    """Lightweight list-row for the Decks detail pane (no free/assigned counts)."""

    oracle_id: str
    name: str
    quantity: int
    role: DeckCardRole
    # Cached Scryfall fields feeding the list's sort / group-by-type controls.
    cmc: float | None = None
    type_line: str | None = None


@dataclass(frozen=True)
class DeckEditLine:
    oracle_id: str
    quantity: int
    role: DeckCardRole


@dataclass(frozen=True)
class FreeCoverage:
    """Free-inventory coverage of a dismantled deck's trackable list slots."""

    covered: int
    required: int


@dataclass(frozen=True)
class CommanderLegalityIssue:
    """A list card that Scryfall marks as not fully legal in Commander."""

    oracle_id: str
    name: str
    legality: str


@dataclass(frozen=True)
class CopyDetail:
    """One physical copy: which edition it is and where it currently lives."""

    copy_id: int
    oracle_id: str
    edition: str | None
    deck_name: str | None


class InventoryService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._copies = CopyRepository(session)

    def add_copy(
        self,
        oracle_id: str,
        quantity: int = 1,
        *,
        edition: str | None = None,
        record_activity: bool = True,
    ) -> list[CardCopy]:
        copies = self._copies.add_many(oracle_id, quantity, edition=edition)
        if record_activity and copies:
            ActivityService(self._session).record_copies_added(
                oracle_id, len(copies)
            )
        return copies

    def remove_free_copies(
        self,
        oracle_id: str,
        quantity: int,
        *,
        record_activity: bool = True,
    ) -> int:
        """Delete up to `quantity` unassigned copies. Returns how many were removed."""
        if quantity <= 0:
            return 0
        free_copies = self._copies.list_free(oracle_id, limit=quantity)
        self._copies.delete_copies(free_copies)
        removed = len(free_copies)
        if record_activity and removed:
            ActivityService(self._session).record_copies_removed(oracle_id, removed)
        return removed

    def set_total_copies(self, oracle_id: str, total: int) -> None:
        """Set physical copy count. Cannot go below copies assigned to armed decks."""
        if total < 0:
            raise ValueError("Copy count cannot be negative")

        current_total = self._copies.count_total(oracle_id)
        assigned = self._copies.count_assigned(oracle_id)
        if total < assigned:
            raise ValueError(
                f"Cannot set total below {assigned} copies assigned to armed decks"
            )

        if total > current_total:
            self.add_copy(oracle_id, total - current_total)
        elif total < current_total:
            removed = self.remove_free_copies(oracle_id, current_total - total)
            if removed != current_total - total:
                raise ValueError("Not enough free copies to remove")

    def free_counts(self) -> dict[str, int]:
        return self._copies.free_counts()

    def list_unassigned_copies(self) -> list[CardCopy]:
        return self._copies.list_all_unassigned()

    def list_copies_with_deck(self, oracle_id: str) -> list[CopyDetail]:
        """Physical copies of a card, with the deck holding each one."""
        return [
            CopyDetail(
                copy_id=copy.id,
                oracle_id=copy.card_id,
                edition=copy.edition,
                deck_name=deck_name,
            )
            for copy, deck_name in self._copies.list_with_deck(oracle_id)
        ]

    def set_copy_editions(self, editions: dict[int, str | None]) -> int:
        """Record set codes per copy. Blank values reset to unspecified."""
        normalized = {
            copy_id: (edition.strip().upper() or None) if edition else None
            for copy_id, edition in editions.items()
        }
        return self._copies.set_editions(normalized)


class DeckService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._decks = DeckRepository(session)
        self._copies = CopyRepository(session)
        self._cards = CardRepository(session)

    def list_decks(self, status: DeckStatus | None = None) -> list[Deck]:
        return self._decks.list_decks(status=status)

    def get_deck(self, deck_id: int) -> Deck | None:
        return self._decks.get(deck_id)

    def next_sort_order(self) -> int:
        current = self._decks.max_sort_order()
        return 0 if current is None else current + 1

    def rename_deck(self, deck_id: int, name: str) -> Deck:
        cleaned = name.strip()
        if not cleaned:
            raise ValueError("Deck name cannot be empty")
        deck = self.get_deck(deck_id)
        if deck is None:
            raise ValueError(f"Deck {deck_id} not found")
        deck.name = cleaned
        self._decks.flush()
        return deck

    def set_format(self, deck_id: int, deck_format: DeckFormat) -> Deck:
        deck = self.get_deck(deck_id)
        if deck is None:
            raise ValueError(f"Deck {deck_id} not found")
        deck.format = deck_format
        self._decks.flush()
        return deck

    def commander_name(self, deck_id: int) -> str | None:
        return self.role_card_name(deck_id, DeckCardRole.COMMANDER)

    def commander_names_by_deck(self) -> dict[int, str]:
        return self._decks.commander_names_by_deck()

    def role_card_name(self, deck_id: int, role: DeckCardRole) -> str | None:
        return self._decks.role_card_name(deck_id, role)

    def command_zone_cards(self, deck_id: int) -> list[tuple[str, str]]:
        """(oracle_id, name) for the command zone, commander first."""
        priority = {
            DeckCardRole.COMMANDER: 0,
            DeckCardRole.PARTNER: 1,
            DeckCardRole.COMPANION: 2,
            DeckCardRole.BACKGROUND: 3,
        }
        rows = self._decks.command_zone_rows(deck_id)
        ordered = sorted(
            rows, key=lambda item: (priority[item[0]], item[2].casefold())
        )
        return [(oracle_id, name) for _role, oracle_id, name in ordered]

    def secondary_command_zone(
        self, deck_id: int
    ) -> tuple[DeckCardRole, str] | None:
        """First Partner / Companion / Background entry, if any."""
        rows = self._decks.secondary_command_zone_rows(deck_id)
        if not rows:
            return None
        priority = {
            DeckCardRole.PARTNER: 0,
            DeckCardRole.COMPANION: 1,
            DeckCardRole.BACKGROUND: 2,
        }
        role, name = min(rows, key=lambda item: (priority[item[0]], item[1].casefold()))
        return role, name

    def set_commander(self, deck_id: int, oracle_id: str | None) -> None:
        self.set_role_card(deck_id, DeckCardRole.COMMANDER, oracle_id)

    def set_role_card(
        self,
        deck_id: int,
        role: DeckCardRole,
        oracle_id: str | None,
    ) -> None:
        """Assign a special-zone role (commander / partner / companion / background).

        Pass ``None`` to clear that role (demoting previous holders to MAIN).
        If ``oracle_id`` is not yet on the list, it is added with quantity 1.
        """
        if role not in {
            DeckCardRole.COMMANDER,
            DeckCardRole.PARTNER,
            DeckCardRole.COMPANION,
            DeckCardRole.BACKGROUND,
        }:
            raise ValueError(f"Unsupported command-zone role: {role}")

        deck = self.get_deck(deck_id)
        if deck is None:
            raise ValueError(f"Deck {deck_id} not found")

        if oracle_id is not None and self._cards.get(oracle_id) is None:
            raise ValueError(f"Card {oracle_id} not found")

        holders = self._decks.list_deck_cards_by_role(deck_id, role)
        for entry in holders:
            if oracle_id is not None and entry.card_id == oracle_id:
                continue
            existing_main = self._decks.get_deck_card(
                deck_id, entry.card_id, DeckCardRole.MAIN
            )
            if existing_main is not None:
                existing_main.quantity += entry.quantity
                self._decks.delete_deck_card(entry)
            else:
                entry.role = DeckCardRole.MAIN

        self._decks.flush()

        if oracle_id is None:
            return

        already = self._decks.get_deck_card(deck_id, oracle_id, role)
        if already is not None:
            return

        # Drop the card from any other special role before assigning.
        for other_role in (
            DeckCardRole.COMMANDER,
            DeckCardRole.PARTNER,
            DeckCardRole.COMPANION,
            DeckCardRole.BACKGROUND,
        ):
            if other_role == role:
                continue
            other = self._decks.get_deck_card(deck_id, oracle_id, other_role)
            if other is not None:
                self._decks.delete_deck_card(other)
        self._decks.flush()

        main_entry = self._decks.get_deck_card(deck_id, oracle_id, DeckCardRole.MAIN)
        if main_entry is not None:
            if main_entry.quantity > 1:
                main_entry.quantity -= 1
            else:
                self._decks.delete_deck_card(main_entry)
            self._decks.flush()

        self._decks.add_deck_card(
            DeckCard(
                deck_id=deck_id,
                card_id=oracle_id,
                quantity=1,
                role=role,
            )
        )
        self._decks.flush()

    def set_secondary_command_zone(
        self,
        deck_id: int,
        role: DeckCardRole | None,
        oracle_id: str | None,
    ) -> None:
        """Set exactly one of Partner / Companion / Background, clearing the others."""
        secondary = {
            DeckCardRole.PARTNER,
            DeckCardRole.COMPANION,
            DeckCardRole.BACKGROUND,
        }
        if role is not None and role not in secondary:
            raise ValueError(f"Secondary role must be partner/companion/background: {role}")
        if role is not None and oracle_id is None:
            raise ValueError("Secondary role requires a card")

        for candidate in secondary:
            if role is not None and candidate == role:
                continue
            self.set_role_card(deck_id, candidate, None)

        if role is not None and oracle_id is not None:
            self.set_role_card(deck_id, role, oracle_id)

    def move_deck(
        self,
        deck_id: int,
        *,
        direction: int,
        status: DeckStatus | None = None,
    ) -> bool:
        """Swap sort_order with the adjacent deck in the (optionally filtered) list.

        ``direction`` is -1 (up) or +1 (down). Returns False if no move occurred.
        """
        if direction not in (-1, 1):
            raise ValueError("direction must be -1 or +1")

        decks = self.list_decks(status=status)
        index = next((i for i, deck in enumerate(decks) if deck.id == deck_id), None)
        if index is None:
            return False
        neighbor_index = index + direction
        if neighbor_index < 0 or neighbor_index >= len(decks):
            return False

        current = decks[index]
        neighbor = decks[neighbor_index]
        current.sort_order, neighbor.sort_order = (
            neighbor.sort_order,
            current.sort_order,
        )
        self._decks.flush()
        return True

    def deck_delete_impact(self, deck_id: int) -> list[DeckDeleteCardImpact]:
        """Inventory impact per trackable card when deleting a deck list."""
        requirements = self.deck_requirements(deck_id)
        if not requirements:
            return []

        totals = self._copies.totals_for_cards(requirements.keys())
        assigned_here = self._copies.assigned_counts_for_deck(
            deck_id, requirements.keys()
        )
        free = InventoryService(self._session).free_counts()

        impacts: list[DeckDeleteCardImpact] = []
        for oracle_id, list_qty in requirements.items():
            card = self._cards.get(oracle_id)
            if card is None:
                continue
            total = totals.get(oracle_id, 0)
            removable = assigned_here.get(oracle_id, 0) + free.get(oracle_id, 0)
            impacts.append(
                DeckDeleteCardImpact(
                    oracle_id=oracle_id,
                    name=card.name,
                    list_quantity=list_qty,
                    total_copies=total,
                    removable_copies=removable,
                )
            )
        return sorted(impacts, key=lambda item: item.name.casefold())

    def delete_deck(
        self,
        deck_id: int,
        remove_copies: dict[str, int] | None = None,
    ) -> bool:
        """Remove a deck list and optionally delete physical copies.

        Removable copies are those assigned to this deck or currently free.
        Copies assigned to other armed decks are never deleted.
        """
        deck = self.get_deck(deck_id)
        if deck is None:
            return False

        deck_name = deck.name
        removals = {
            oracle_id: qty
            for oracle_id, qty in (remove_copies or {}).items()
            if qty > 0
        }
        if removals:
            self._delete_removable_copies(deck_id, removals)

        self._decks.delete_assignments_for_deck(deck.id)
        self._decks.delete_deck_cards(deck.id)
        self._decks.delete(deck)
        ActivityService(self._session).record(
            ActivityEventType.DECK_DELETED,
            "history.event.deck_deleted",
            {
                "deck_id": deck_id,
                "deck_name": deck_name,
                "copies_removed": sum(removals.values()) if removals else 0,
            },
        )
        return True

    def _delete_removable_copies(
        self, deck_id: int, removals: dict[str, int]
    ) -> None:
        for oracle_id, quantity in removals.items():
            remaining = quantity
            if remaining <= 0:
                continue

            assigned = self._copies.list_assigned_to_deck(
                deck_id, oracle_id, limit=remaining
            )
            for copy in assigned:
                self._copies.delete_assignment_for_copy(copy.id)
                self._session.delete(copy)
                remaining -= 1

            if remaining <= 0:
                continue

            free_copies = self._copies.list_free(oracle_id, limit=remaining)
            for copy in free_copies:
                self._session.delete(copy)

        self._decks.flush()

    def deck_card_summaries(self, deck_id: int) -> list[DeckCardSummary]:
        """Cards on a deck list for display, command zone first then by name."""
        rows = self._decks.list_deck_cards_with_card(deck_id, exclude_token=True)
        priority = {
            DeckCardRole.COMMANDER: 0,
            DeckCardRole.PARTNER: 1,
            DeckCardRole.COMPANION: 2,
            DeckCardRole.BACKGROUND: 3,
            DeckCardRole.MAIN: 4,
        }
        summaries = [
            DeckCardSummary(
                oracle_id=card.oracle_id,
                name=card.name,
                quantity=deck_card.quantity,
                role=deck_card.role,
                cmc=card.cmc,
                type_line=card.type_line,
            )
            for deck_card, card in rows
        ]
        return sorted(
            summaries,
            key=lambda row: (priority.get(row.role, 99), row.name.casefold()),
        )

    def deck_statistics(self, deck_id: int) -> DeckStatistics:
        """Counts, average mana value, pips and mana curve for the detail pane."""
        rows = self._decks.list_deck_cards_with_card(
            deck_id, exclude_token=True, order_by_name=False
        )
        cards = [
            DeckStatsCard(
                name=card.name,
                quantity=deck_card.quantity,
                type_line=card.type_line,
                cmc=card.cmc,
                mana_cost=card.mana_cost,
                is_basic_land=card.is_basic_land,
            )
            for deck_card, card in rows
        ]
        return compute_deck_statistics(cards)

    def deck_edit_rows(self, deck_id: int) -> list[DeckEditRow]:
        rows = self._decks.list_deck_cards_with_card(deck_id, exclude_token=True)
        if not rows:
            return []

        oracle_ids = {card.oracle_id for _, card in rows}
        free = InventoryService(self._session).free_counts()
        assigned_here = self._copies.assigned_counts_for_deck(deck_id, oracle_ids)

        return [
            DeckEditRow(
                oracle_id=card.oracle_id,
                name=card.name,
                quantity=deck_card.quantity,
                role=deck_card.role,
                free_copies=free.get(card.oracle_id, 0),
                is_basic_land=card.is_basic_land,
                is_token=card.is_token,
                removable_copies=(
                    assigned_here.get(card.oracle_id, 0) + free.get(card.oracle_id, 0)
                ),
                commander_legality=card.commander_legality,
            )
            for deck_card, card in rows
        ]

    def apply_deck_edit(
        self,
        deck_id: int,
        lines: list[DeckEditLine],
        *,
        create_free_copies: dict[str, int] | None = None,
        remove_copies: dict[str, int] | None = None,
    ) -> None:
        deck = self.get_deck(deck_id)
        if deck is None:
            raise ValueError(f"Deck {deck_id} not found")

        was_armed = deck.status == DeckStatus.ARMED
        if was_armed:
            self.set_status(deck, DeckStatus.DISMANTLED, record_activity=False)

        removals = {
            oracle_id: qty
            for oracle_id, qty in (remove_copies or {}).items()
            if qty > 0
        }
        if removals:
            self._delete_removable_copies(deck_id, removals)

        creations = {
            oracle_id: qty
            for oracle_id, qty in (create_free_copies or {}).items()
            if qty > 0
        }
        if creations:
            inventory = InventoryService(self._session)
            for oracle_id, qty in creations.items():
                inventory.add_copy(oracle_id, qty, record_activity=False)

        self._decks.delete_deck_cards(deck.id)

        merged: dict[tuple[str, DeckCardRole], int] = {}
        for line in lines:
            if line.quantity <= 0:
                continue
            key = (line.oracle_id, line.role)
            merged[key] = merged.get(key, 0) + line.quantity

        for (oracle_id, role), quantity in merged.items():
            self._decks.add_deck_card(
                DeckCard(
                    deck_id=deck.id,
                    card_id=oracle_id,
                    quantity=quantity,
                    role=role,
                )
            )
        self._decks.flush()

        if was_armed:
            self.set_status(deck, DeckStatus.ARMED, record_activity=False)

        self._session.refresh(deck)
        ActivityService(self._session).record(
            ActivityEventType.DECK_LIST_EDITED,
            "history.event.deck_list_edited",
            {"deck_id": deck.id, "deck_name": deck.name},
        )

    def set_status(
        self,
        deck: Deck,
        status: DeckStatus,
        *,
        record_activity: bool = True,
    ) -> None:
        if status == DeckStatus.DISMANTLED:
            self._decks.delete_assignments_for_deck(deck.id)
            deck.status = status
            if record_activity:
                ActivityService(self._session).record(
                    ActivityEventType.DECK_DISMANTLED,
                    "history.event.deck_dismantled",
                    {"deck_id": deck.id, "deck_name": deck.name},
                )
            return

        if status == DeckStatus.ARMED:
            deck.status = status
            self._ensure_assignments(deck)
            if record_activity:
                ActivityService(self._session).record(
                    ActivityEventType.DECK_ARMED,
                    "history.event.deck_armed",
                    {"deck_id": deck.id, "deck_name": deck.name},
                )
            return

        deck.status = status

    def _ensure_assignments(self, deck: Deck) -> None:
        assigned_counts: dict[str, int] = {}
        for assignment in deck.assignments:
            card_id = assignment.card_copy.card_id
            assigned_counts[card_id] = assigned_counts.get(card_id, 0) + 1

        for card_id, required in self.deck_requirements(deck.id).items():
            missing = required - assigned_counts.get(card_id, 0)
            if missing <= 0:
                continue

            free_copies = self._copies.list_free(card_id, limit=missing)
            for copy in free_copies:
                self._copies.add_assignment(copy.id, deck.id)
                missing -= 1

            for _ in range(missing):
                copy = self._copies.add(card_id)
                self._decks.flush()
                self._copies.add_assignment(copy.id, deck.id)

        self._decks.flush()

    def deck_requirements(self, deck_id: int) -> dict[str, int]:
        return self._decks.requirements(deck_id)

    def deck_basic_lands(self, deck_id: int) -> dict[str, int]:
        """Basic land quantities on the list (unlimited pool; not optimized)."""
        return self._decks.basic_land_requirements(deck_id)

    def set_locked(self, deck: Deck, locked: bool) -> Deck:
        deck.is_locked = locked
        self._session.flush()
        return deck

    def armed_deck_supplies(
        self,
        exclude_deck_id: int | None = None,
        *,
        include_locked: bool = False,
    ) -> dict[int, dict[str, int]]:
        """Supplies from armed decks. Locked decks are excluded by default."""
        supplies: dict[int, dict[str, int]] = {}
        for deck in self._decks.list_armed(
            exclude_deck_id=exclude_deck_id,
            include_locked=include_locked,
        ):
            supplies[deck.id] = self.deck_requirements(deck.id)
        return supplies

    def free_coverage_toward_deck(self, deck_id: int) -> FreeCoverage:
        """How many trackable list copies are already covered by free inventory."""
        requirements = self.deck_requirements(deck_id)
        required = sum(requirements.values())
        if required == 0:
            return FreeCoverage(covered=0, required=0)
        free = InventoryService(self._session).free_counts()
        covered = sum(
            min(need, free.get(card_id, 0))
            for card_id, need in requirements.items()
        )
        return FreeCoverage(covered=covered, required=required)

    def commander_legality_issues(
        self, deck_id: int
    ) -> list[CommanderLegalityIssue]:
        """Cards on the list with Scryfall Commander legality issues (advisory)."""
        issues: list[CommanderLegalityIssue] = []
        for oracle_id, name, legality in self._decks.commander_legality_rows(deck_id):
            if not is_scryfall_legality_issue(legality):
                continue
            issues.append(
                CommanderLegalityIssue(
                    oracle_id=oracle_id,
                    name=name,
                    legality=str(legality),
                )
            )
        return sorted(issues, key=lambda item: item.name.casefold())

    def commander_rule_issues(self, deck_id: int) -> list[CommanderRuleIssue]:
        """Game-rule warnings for the list (advisory; never blocks arming)."""
        deck = self.get_deck(deck_id)
        if deck is None:
            return []
        cards = [
            CommanderCard(
                oracle_id=oracle_id,
                name=name,
                role=role,
                color_identity=color_identity,
                oracle_text=oracle_text,
                type_line=type_line,
                quantity=quantity,
                is_basic_land=is_basic_land,
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
            ) in self._decks.commander_rule_rows(deck_id)
        ]
        return profile_for(deck.format).evaluate(cards)

    def rule_issues(self, deck_id: int) -> list[CommanderRuleIssue]:
        """Alias for :meth:`commander_rule_issues` (format-aware dispatch)."""
        return self.commander_rule_issues(deck_id)
