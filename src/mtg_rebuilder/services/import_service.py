from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from mtg_rebuilder.algorithms.card_utils import is_basic_land_name
from mtg_rebuilder.api.archidekt_client import fetch_archidekt_deck
from mtg_rebuilder.api.moxfield_client import fetch_moxfield_deck
from mtg_rebuilder.models import Card, CardCopy, Deck, DeckCard
from mtg_rebuilder.models.enums import (
    ActivityEventType,
    DeckCardRole,
    DeckFormat,
    DeckStatus,
)
from mtg_rebuilder.repositories import CardRepository, CopyRepository, DeckRepository
from mtg_rebuilder.services.activity_service import ActivityService
from mtg_rebuilder.services.deck_service import (
    DeckEditRow,
    DeckService,
    InventoryService,
)
from mtg_rebuilder.services.decklist_parser import (
    ARENA_SECTION_RE,
    CATEGORY_HEADER_RE,
    DecklistFormat,
    ParsedDeckLine,
    detect_format,
    extract_archidekt_deck_id,
    extract_moxfield_deck_id,
    parse_decklist,
    parse_moxfield_line,
)
from mtg_rebuilder.services.deck_export import (
    ExportFormat,
    format_deck_export,
    load_deck_export_cards,
)
from mtg_rebuilder.services.scryfall_service import ScryfallService

SECONDARY_ROLE_FROM_NAME: dict[str, DeckCardRole] = {
    "partner": DeckCardRole.PARTNER,
    "companion": DeckCardRole.COMPANION,
    "background": DeckCardRole.BACKGROUND,
}


@dataclass
class ImportWarning:
    line: str
    message: str


@dataclass
class TrackableDeckCard:
    oracle_id: str
    name: str
    quantity: int


@dataclass
class ImportResult:
    deck: Deck
    warnings: list[ImportWarning] = field(default_factory=list)


@dataclass(frozen=True)
class InventoryListCard:
    oracle_id: str
    name: str
    list_quantity: int
    # Set code from the pasted line, when every line for this card agreed.
    set_code: str | None = None
    # ``foil`` only when every line carried ``*F*``. Missing ``*F*`` stays None.
    finish: str | None = None
    # Collector number when every line for this card agreed.
    collector_number: str | None = None


@dataclass(frozen=True)
class InventoryListPreview:
    identified: list[InventoryListCard]
    unresolved_lines: list[str]


@dataclass(frozen=True)
class DeckListChange:
    oracle_id: str
    name: str
    before: int
    after: int

    @property
    def delta(self) -> int:
        return self.after - self.before


@dataclass(frozen=True)
class DeckListUpdatePreview:
    """Diff between a deck's stored list and a pasted/fetched replacement."""

    text: str
    deck_name: str | None
    commander_name: str | None
    secondary_role: DeckCardRole | None
    secondary_name: str | None
    added: list[DeckListChange]
    removed: list[DeckListChange]
    total_before: int
    total_after: int
    unresolved_lines: list[str]
    edit_rows: list[DeckEditRow] = field(default_factory=list)
    # List printings that no current copy already records. Empty unless the
    # user already owns that card and the list adds set, foil, or number.
    print_placements: list[PrintPlacement] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.removed)


@dataclass(frozen=True)
class ResolvedDecklistInput:
    """Paste/file/URL materializado a texto de listado + metadatos opcionales."""

    text: str
    format: DecklistFormat
    deck_name: str | None = None
    commander_name: str | None = None
    secondary_role: DeckCardRole | None = None
    secondary_name: str | None = None


def _agree(left: str | None, right: str | None) -> str | None:
    """Keep a print fact only when both lines carried the same value."""
    if left == right:
        return left
    return None


@dataclass(frozen=True)
class PrintPlacement:
    """One printing on a deck list that inventory copies do not already record.

    ``quantity`` is how many of these are still unexplained: a copy counts as
    already recorded only when it has every fact the line states. The user
    then says how many of that remainder are new physical copies. The rest
    are treated as copies already in inventory, and those rows are not edited.
    """

    oracle_id: str
    name: str
    quantity: int
    set_code: str | None = None
    finish: str | None = None
    collector_number: str | None = None


def format_print_placement(placement: PrintPlacement) -> str:
    """Short label for the facts the list added, e.g. ``C21 263 foil``."""
    parts: list[str] = []
    if placement.set_code:
        parts.append(placement.set_code)
    if placement.collector_number:
        parts.append(placement.collector_number)
    if placement.finish:
        parts.append(placement.finish)
    return " ".join(parts)


def _copy_covers_printing(
    edition: str | None,
    finish: str | None,
    collector_number: str | None,
    set_code: str | None,
    listed_finish: str | None,
    listed_collector: str | None,
) -> bool:
    """True when the copy already has every fact this list line states."""
    if set_code is not None and edition != set_code:
        return False
    if listed_finish is not None and finish != listed_finish:
        return False
    if listed_collector is not None and collector_number != listed_collector:
        return False
    return True


def ambiguous_print_placements(
    lines: list[tuple[str, str, int, str | None, str | None, str | None]],
    copies: list[tuple[str, str | None, str | None, str | None]],
) -> list[PrintPlacement]:
    """Printings to ask about when a deck list is applied.

    ``lines`` are ``(oracle_id, name, quantity, set_code, finish, collector)``.
    ``copies`` are ``(oracle_id, edition, finish, collector_number)``.

    Lines with no set, foil, or number are skipped. A card with no physical
    copies is skipped too: nothing in inventory could be the same card, so
    the list update does not invent copies from the printing. Each copy can
    cover only one listed copy, and more specific printings are matched first.
    """
    grouped: dict[tuple[str, str | None, str | None, str | None], int] = {}
    names: dict[str, str] = {}
    for oracle_id, name, quantity, set_code, finish, collector in lines:
        if quantity <= 0:
            continue
        if set_code is None and finish is None and collector is None:
            continue
        names[oracle_id] = name
        key = (oracle_id, set_code, finish, collector)
        grouped[key] = grouped.get(key, 0) + quantity

    pool: dict[str, list[tuple[str | None, str | None, str | None]]] = {}
    for oracle_id, edition, finish, collector in copies:
        pool.setdefault(oracle_id, []).append((edition, finish, collector))

    def specificity(
        key: tuple[str, str | None, str | None, str | None],
    ) -> int:
        return sum(part is not None for part in key[1:])

    placements: list[PrintPlacement] = []
    for oracle_id in sorted(names, key=lambda card_id: names[card_id].casefold()):
        owned = pool.get(oracle_id, [])
        if not owned:
            continue
        used = [False] * len(owned)
        keys = sorted(
            (key for key in grouped if key[0] == oracle_id),
            key=lambda key: (
                -specificity(key),
                key[1] or "",
                key[3] or "",
                key[2] or "",
            ),
        )
        for key in keys:
            _oracle_id, set_code, finish, collector = key
            needed = grouped[key]
            matched = 0
            for index, (edition, copy_finish, copy_collector) in enumerate(owned):
                if used[index] or matched >= needed:
                    continue
                if _copy_covers_printing(
                    edition, copy_finish, copy_collector, set_code, finish, collector
                ):
                    used[index] = True
                    matched += 1
            remaining = needed - matched
            if remaining <= 0:
                continue
            placements.append(
                PrintPlacement(
                    oracle_id=oracle_id,
                    name=names[oracle_id],
                    quantity=remaining,
                    set_code=set_code,
                    finish=finish,
                    collector_number=collector,
                )
            )
    return placements


class ImportService:
    def __init__(self, session: Session, scryfall: ScryfallService) -> None:
        self._session = session
        self._scryfall = scryfall
        self._decks = DeckRepository(session)
        self._cards = CardRepository(session)
        self._copies = CopyRepository(session)

    def resolve_decklist_input(
        self,
        text: str,
        *,
        fetch_url: bool = True,
    ) -> ResolvedDecklistInput:
        """Expand a Moxfield/Archidekt URL when needed; otherwise return text as-is."""
        stripped = text.strip()
        fmt = detect_format(stripped)
        if fmt not in (DecklistFormat.MOXFIELD_URL, DecklistFormat.ARCHIDEKT_URL):
            return ResolvedDecklistInput(text=stripped, format=fmt)

        if not fetch_url:
            raise ValueError("Deck URL requires network fetch")

        if fmt == DecklistFormat.MOXFIELD_URL:
            deck_id = extract_moxfield_deck_id(stripped)
            if deck_id is None:
                raise ValueError("Could not parse Moxfield deck URL")
            export = fetch_moxfield_deck(deck_id)
            list_format = DecklistFormat.MOXFIELD_MTGO
        else:
            deck_id = extract_archidekt_deck_id(stripped)
            if deck_id is None:
                raise ValueError("Could not parse Archidekt deck URL")
            export = fetch_archidekt_deck(deck_id)
            list_format = DecklistFormat.ARCHIDEKT

        secondary_role = None
        if export.secondary_role:
            secondary_role = SECONDARY_ROLE_FROM_NAME.get(
                export.secondary_role.lower()
            )
        return ResolvedDecklistInput(
            text=export.list_text,
            format=list_format,
            deck_name=export.name,
            commander_name=export.commander_name,
            secondary_role=secondary_role,
            secondary_name=export.secondary_name,
        )

    def preview_inventory_list(self, text: str) -> InventoryListPreview:
        """Resolve decklist text into inventoriable cards + unresolved lines.

        Basics and tokens are skipped (not trackable). Supports Moxfield/MTGO,
        Arena, Archidekt, MTGO .dek, and Moxfield / Archidekt URLs (fetched).
        """
        resolved = self.resolve_decklist_input(text)
        body = resolved.text
        fmt = resolved.format

        merged: dict[str, InventoryListCard] = {}
        unresolved: list[str] = []

        parsed_lines = parse_decklist(body)
        for parsed in parsed_lines:
            try:
                card = self._scryfall.fetch_and_cache(
                    parsed.name,
                    prefer_token=parsed.role == DeckCardRole.TOKEN,
                )
            except Exception:
                unresolved.append(parsed.raw_line.strip())
                continue

            if is_basic_land_name(parsed.name) or card.is_basic_land or card.is_token:
                continue

            finish = "foil" if parsed.foil else None
            existing = merged.get(card.oracle_id)
            if existing is None:
                merged[card.oracle_id] = InventoryListCard(
                    oracle_id=card.oracle_id,
                    name=card.name,
                    list_quantity=parsed.quantity,
                    set_code=parsed.set_code,
                    finish=finish,
                    collector_number=parsed.collector_number,
                )
            else:
                # Same card listed twice with different print facts: that
                # field is ambiguous, so drop it rather than guess. Quantity
                # still adds. A line without ``*F*`` does not mean nonfoil,
                # but it also does not agree with a line that has ``*F*``.
                merged[card.oracle_id] = InventoryListCard(
                    oracle_id=card.oracle_id,
                    name=card.name,
                    list_quantity=existing.list_quantity + parsed.quantity,
                    set_code=_agree(existing.set_code, parsed.set_code),
                    finish=_agree(existing.finish, finish),
                    collector_number=_agree(
                        existing.collector_number, parsed.collector_number
                    ),
                )

        unresolved.extend(self._unparsed_lines(body, fmt, parsed_lines))

        identified = sorted(merged.values(), key=lambda c: c.name.casefold())
        return InventoryListPreview(
            identified=identified,
            unresolved_lines=unresolved,
        )

    def preview_deck_list_update(
        self,
        deck_id: int,
        text: str,
        commander_name: str | None = None,
    ) -> DeckListUpdatePreview:
        """Diff a deck's current list against pasted text (or a Moxfield URL)."""
        deck = self._decks.get(deck_id)
        if deck is None:
            raise ValueError(f"Deck {deck_id} not found")

        resolved = self.resolve_decklist_input(text)
        parsed_lines = parse_decklist(resolved.text)
        commander = commander_name or resolved.commander_name

        after_roles: dict[tuple[str, DeckCardRole], int] = {}
        after_cards: dict[str, Card] = {}
        after: dict[str, int] = {}
        names: dict[str, str] = {}
        unresolved: list[str] = []
        print_lines: list[
            tuple[str, str, int, str | None, str | None, str | None]
        ] = []
        for line in parsed_lines:
            try:
                card = self._scryfall.fetch_and_cache(
                    line.name,
                    prefer_token=line.role == DeckCardRole.TOKEN,
                )
            except Exception:
                unresolved.append(line.raw_line.strip())
                continue
            # Tokens are not tracked on deck lists.
            if line.role == DeckCardRole.TOKEN or card.is_token:
                continue
            if is_basic_land_name(line.name):
                card.is_basic_land = True
            role = line.role
            if commander and line.name.lower() == commander.lower():
                role = DeckCardRole.COMMANDER
            after_roles[(card.oracle_id, role)] = (
                after_roles.get((card.oracle_id, role), 0) + line.quantity
            )
            after[card.oracle_id] = after.get(card.oracle_id, 0) + line.quantity
            after_cards[card.oracle_id] = card
            names[card.oracle_id] = card.name
            if not card.is_basic_land:
                listed_finish = "foil" if line.foil else None
                if line.set_code or listed_finish or line.collector_number:
                    print_lines.append(
                        (
                            card.oracle_id,
                            card.name,
                            line.quantity,
                            line.set_code,
                            listed_finish,
                            line.collector_number,
                        )
                    )

        unresolved.extend(
            self._unparsed_lines(resolved.text, resolved.format, parsed_lines)
        )
        if commander:
            self._promote_commander_plan(after_roles, after_cards, commander)

        before: dict[str, int] = {}
        rows = self._decks.list_deck_cards_with_card(deck_id, order_by_name=False)
        for deck_card, card in rows:
            before[card.oracle_id] = before.get(card.oracle_id, 0) + deck_card.quantity
            names.setdefault(card.oracle_id, card.name)

        added: list[DeckListChange] = []
        removed: list[DeckListChange] = []
        for oracle_id in before.keys() | after.keys():
            old = before.get(oracle_id, 0)
            new = after.get(oracle_id, 0)
            if old == new:
                continue
            change = DeckListChange(
                oracle_id=oracle_id,
                name=names.get(oracle_id, oracle_id),
                before=old,
                after=new,
            )
            (added if new > old else removed).append(change)

        listed_ids = {oracle_id for oracle_id, *_rest in print_lines}
        copy_rows = (
            [
                (
                    copy.card_id,
                    copy.edition,
                    copy.finish,
                    copy.collector_number,
                )
                for copy in self._session.scalars(
                    select(CardCopy).where(CardCopy.card_id.in_(listed_ids))
                )
            ]
            if listed_ids
            else []
        )

        return DeckListUpdatePreview(
            text=resolved.text,
            deck_name=resolved.deck_name,
            commander_name=resolved.commander_name,
            secondary_role=resolved.secondary_role,
            secondary_name=resolved.secondary_name,
            added=sorted(added, key=lambda change: change.name.casefold()),
            removed=sorted(removed, key=lambda change: change.name.casefold()),
            total_before=sum(before.values()),
            total_after=sum(after.values()),
            unresolved_lines=unresolved,
            edit_rows=self._edit_rows_for_update(deck_id, after_roles, after_cards),
            print_placements=ambiguous_print_placements(print_lines, copy_rows),
        )

    def _promote_commander_plan(
        self,
        after_roles: dict[tuple[str, DeckCardRole], int],
        after_cards: dict[str, Card],
        commander_name: str,
    ) -> None:
        card = self._scryfall.lookup_local(commander_name)
        if card is None:
            return
        main_qty = after_roles.get((card.oracle_id, DeckCardRole.MAIN), 0)
        cmd_qty = after_roles.get((card.oracle_id, DeckCardRole.COMMANDER), 0)
        if cmd_qty > 0 or main_qty <= 0:
            return
        after_roles[(card.oracle_id, DeckCardRole.COMMANDER)] = 1
        leftover = main_qty - 1
        if leftover > 0:
            after_roles[(card.oracle_id, DeckCardRole.MAIN)] = leftover
        else:
            after_roles.pop((card.oracle_id, DeckCardRole.MAIN), None)
        after_cards[card.oracle_id] = card

    def _edit_rows_for_update(
        self,
        deck_id: int,
        after_roles: dict[tuple[str, DeckCardRole], int],
        after_cards: dict[str, Card],
    ) -> list[DeckEditRow]:
        if not after_roles:
            return []
        oracle_ids = {oracle_id for oracle_id, _role in after_roles}
        free = InventoryService(self._session).free_counts()
        assigned_here = self._copies.assigned_counts_for_deck(deck_id, oracle_ids)
        rows: list[DeckEditRow] = []
        for (oracle_id, role), quantity in after_roles.items():
            if quantity <= 0:
                continue
            card = after_cards.get(oracle_id)
            if card is None:
                continue
            rows.append(
                DeckEditRow(
                    oracle_id=oracle_id,
                    name=card.name,
                    quantity=quantity,
                    role=role,
                    free_copies=free.get(oracle_id, 0),
                    is_basic_land=card.is_basic_land,
                    is_token=card.is_token,
                    removable_copies=(
                        assigned_here.get(oracle_id, 0) + free.get(oracle_id, 0)
                    ),
                    commander_legality=card.commander_legality,
                )
            )
        return sorted(rows, key=lambda row: (row.name.casefold(), row.role.value))

    def _unparsed_lines(
        self,
        body: str,
        fmt: DecklistFormat,
        parsed_lines: list[ParsedDeckLine],
    ) -> list[str]:
        """Non-empty lines that are neither headers nor valid card lines."""
        if fmt == DecklistFormat.MTGO_DEK:
            return []

        parsed_raw = {line.raw_line.strip() for line in parsed_lines}
        leftovers: list[str] = []
        for raw in body.splitlines():
            stripped = raw.strip()
            if not stripped:
                continue
            if CATEGORY_HEADER_RE.match(stripped) or ARENA_SECTION_RE.match(stripped):
                continue
            if stripped in parsed_raw:
                continue
            if parse_moxfield_line(raw) is not None:
                continue
            leftovers.append(stripped)
        return leftovers

    def import_decklist_text(
        self,
        *,
        deck_name: str,
        text: str,
        status: DeckStatus = DeckStatus.DISMANTLED,
        commander_name: str | None = None,
        deck_format: DeckFormat = DeckFormat.COMMANDER,
    ) -> ImportResult:
        resolved = self.resolve_decklist_input(text)
        parsed_lines = parse_decklist(resolved.text)

        deck = Deck(
            name=deck_name,
            status=status,
            format=deck_format,
            sort_order=DeckService(self._session).next_sort_order(),
        )
        self._decks.add(deck)

        warnings = self._populate_deck_cards(
            deck.id,
            parsed_lines=parsed_lines,
            commander_name=commander_name,
        )

        self._session.refresh(deck)
        ActivityService(self._session).record(
            ActivityEventType.DECK_IMPORTED,
            "history.event.deck_imported",
            {
                "deck_id": deck.id,
                "deck_name": deck.name,
                "status": status.value,
            },
        )
        return ImportResult(deck=deck, warnings=warnings)

    def import_moxfield_text(
        self,
        *,
        deck_name: str,
        text: str,
        status: DeckStatus = DeckStatus.DISMANTLED,
        commander_name: str | None = None,
    ) -> ImportResult:
        """Backward-compatible alias for import_decklist_text."""
        return self.import_decklist_text(
            deck_name=deck_name,
            text=text,
            status=status,
            commander_name=commander_name,
        )

    def deck_to_moxfield_text(self, deck_id: int) -> str:
        return self.deck_to_text(deck_id, ExportFormat.MOXFIELD)

    def deck_to_text(self, deck_id: int, fmt: ExportFormat) -> str:
        cards = load_deck_export_cards(self._session, deck_id)
        return format_deck_export(cards, fmt)

    def replace_deck_list(
        self,
        deck_id: int,
        text: str,
        commander_name: str | None = None,
    ) -> list[ImportWarning]:
        deck = self._decks.get(deck_id)
        if deck is None:
            raise ValueError(f"Deck {deck_id} not found")

        deck_service = DeckService(self._session)
        was_armed = deck.status == DeckStatus.ARMED
        if was_armed:
            deck_service.set_status(
                deck, DeckStatus.DISMANTLED, record_activity=False
            )

        for deck_card in list(deck.cards):
            self._decks.delete_deck_card(deck_card)
        self._decks.flush()

        resolved = self.resolve_decklist_input(text)
        parsed_lines = parse_decklist(resolved.text)
        warnings = self._populate_deck_cards(
            deck.id,
            parsed_lines=parsed_lines,
            commander_name=commander_name,
        )

        if was_armed:
            deck_service.set_status(deck, DeckStatus.ARMED, record_activity=False)

        self._session.refresh(deck)
        ActivityService(self._session).record(
            ActivityEventType.DECK_LIST_EDITED,
            "history.event.deck_list_edited",
            {"deck_id": deck.id, "deck_name": deck.name},
        )
        return warnings

    def _populate_deck_cards(
        self,
        deck_id: int,
        *,
        parsed_lines: list[ParsedDeckLine],
        commander_name: str | None = None,
    ) -> list[ImportWarning]:
        warnings: list[ImportWarning] = []
        # One row per (oracle_id, role): reprints of the same card ("2 Island
        # (FRA) 283" + "1 Island (FRA) 284") share an identity and must merge.
        merged: dict[tuple[str, DeckCardRole], int] = {}

        for line in parsed_lines:
            # Tokens are unlimited / display-only elsewhere; never store on lists.
            if line.role == DeckCardRole.TOKEN:
                continue
            try:
                card = self._scryfall.fetch_and_cache(
                    line.name,
                    prefer_token=False,
                )
            except Exception as exc:
                warnings.append(
                    ImportWarning(line=line.raw_line, message=str(exc))
                )
                continue

            if card.is_token:
                continue

            if is_basic_land_name(line.name):
                card.is_basic_land = True

            role = line.role
            if commander_name and line.name.lower() == commander_name.lower():
                role = DeckCardRole.COMMANDER

            key = (card.oracle_id, role)
            merged[key] = merged.get(key, 0) + line.quantity

        for (oracle_id, role), quantity in merged.items():
            self._upsert_deck_card(deck_id, oracle_id, quantity, role)

        if commander_name:
            self._promote_commander(deck_id, commander_name)

        self._decks.flush()
        return warnings

    def list_trackable_cards(self, deck_id: int) -> list[TrackableDeckCard]:
        requirements = DeckService(self._session).deck_requirements(deck_id)
        cards: list[TrackableDeckCard] = []
        for oracle_id, quantity in requirements.items():
            card = self._cards.get(oracle_id)
            if card is None:
                continue
            cards.append(
                TrackableDeckCard(
                    oracle_id=oracle_id,
                    name=card.name,
                    quantity=quantity,
                )
            )
        return sorted(cards, key=lambda entry: entry.name.casefold())

    def add_confirmed_print_copies(
        self,
        choices: list[tuple[PrintPlacement, int]],
    ) -> int:
        """Create copies the user marked as new during a deck-list update.

        Does not edit copies that already exist. A count of zero adds nothing:
        those listed copies are the ones already in inventory, and their
        details stay as they were. Counts above the asked quantity are capped.
        """
        inventory = InventoryService(self._session)
        added = 0
        for placement, count in choices:
            if count <= 0:
                continue
            creating = min(count, placement.quantity)
            inventory.add_copy(
                placement.oracle_id,
                creating,
                edition=placement.set_code,
                finish=placement.finish,
                collector_number=placement.collector_number,
            )
            added += creating
        return added

    def apply_available_copies(
        self,
        quantities: dict[str, int],
        editions: dict[str, str | None] | None = None,
        finishes: dict[str, str | None] | None = None,
        collector_numbers: dict[str, str | None] | None = None,
    ) -> int:
        """Create new free copies. Does not update copies that already exist.

        Empty finish or collector number on this call leaves those fields
        empty on the new rows and does not clear them on older rows.
        """
        inventory = InventoryService(self._session)
        added = 0
        for oracle_id, quantity in quantities.items():
            if quantity <= 0:
                continue
            inventory.add_copy(
                oracle_id,
                quantity,
                edition=(editions or {}).get(oracle_id),
                finish=(finishes or {}).get(oracle_id),
                collector_number=(collector_numbers or {}).get(oracle_id),
                record_activity=True,
            )
            added += quantity
        return added

    def _upsert_deck_card(
        self,
        deck_id: int,
        card_id: str,
        quantity: int,
        role: DeckCardRole,
    ) -> None:
        existing = self._decks.get_deck_card(deck_id, card_id, role)
        if existing:
            existing.quantity += quantity
            return

        self._decks.add_deck_card(
            DeckCard(
                deck_id=deck_id,
                card_id=card_id,
                quantity=quantity,
                role=role,
            )
        )

    def _promote_commander(self, deck_id: int, commander_name: str) -> None:
        card = self._scryfall.lookup_local(commander_name)
        if card is None:
            return

        main_entry = self._decks.get_deck_card(
            deck_id, card.oracle_id, DeckCardRole.MAIN
        )
        if main_entry is None:
            return

        if main_entry.quantity > 1:
            main_entry.quantity -= 1
        else:
            self._decks.delete_deck_card(main_entry)

        self._upsert_deck_card(deck_id, card.oracle_id, 1, DeckCardRole.COMMANDER)
