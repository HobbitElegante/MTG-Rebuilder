from dataclasses import dataclass

from sqlalchemy.orm import Session

from mtg_rebuilder.repositories import (
    CardPrintRepository,
    CardRepository,
    CopyRepository,
    DeckRepository,
)
from mtg_rebuilder.services.scryfall_bulk_service import BulkSyncStatus, ScryfallBulkService


@dataclass(frozen=True)
class OverviewStats:
    cards: int
    copies: int
    unassigned_copies: int
    decks: int
    armed_decks: int
    deck_cards: int
    assignments: int


@dataclass(frozen=True)
class CardSummary:
    oracle_id: str
    name: str
    type_line: str | None
    cmc: float | None
    color_identity: str | None
    is_basic_land: bool
    is_token: bool
    copy_count: int
    commander_legality: str | None = None


@dataclass(frozen=True)
class InventorySummaryRow:
    oracle_id: str
    card_name: str
    total_copies: int
    free_copies: int
    assigned_decks: tuple[str, ...]
    color_identity: str | None = None
    # (set code or None for unspecified, copies) — only populated when the
    # edition-tracking setting is on.
    editions: tuple[tuple[str | None, int], ...] = ()
    type_line: str | None = None
    colors: str | None = None
    cmc: float | None = None
    # Scryfall brace string (``{2}{W/U}``); empty for lands, None when unknown.
    mana_cost: str | None = None
    # Representative Scryfall rarity (bulk / lookup).
    rarity: str | None = None
    # Effective rarities for filtering: Card.rarity and/or per-edition CardPrint
    # rarities when editions are tracked (falls back to Card.rarity).
    rarities: frozenset[str] = frozenset()
    oracle_text: str | None = None
    commander_legality: str | None = None
    is_basic_land: bool = False
    is_token: bool = False
    # Deck ids that currently hold a physical copy of this card.
    assigned_deck_ids: frozenset[int] = frozenset()


def _sorted_editions(
    counts: dict[str | None, int],
) -> tuple[tuple[str | None, int], ...]:
    """Most copies first; unspecified last so real set codes lead the summary."""
    return tuple(
        sorted(
            counts.items(),
            key=lambda item: (item[0] is None, -item[1], item[0] or ""),
        )
    )


def _effective_rarities(
    card_rarity: str | None,
    editions: tuple[tuple[str | None, int], ...],
    *,
    include_editions: bool,
    print_rarities: dict[tuple[str, str], str | None],
    oracle_id: str,
) -> frozenset[str]:
    """Rarities present on this inventory row (path A, or A+B with editions)."""
    if not include_editions or not editions:
        return frozenset({card_rarity}) if card_rarity else frozenset()

    found: set[str] = set()
    for set_code, _count in editions:
        if set_code:
            print_rarity = print_rarities.get((oracle_id, set_code.upper()))
            if print_rarity:
                found.add(print_rarity)
            elif card_rarity:
                found.add(card_rarity)
        elif card_rarity:
            found.add(card_rarity)
    return frozenset(found)


class BrowseService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._cards = CardRepository(session)
        self._copies = CopyRepository(session)
        self._decks = DeckRepository(session)
        self._prints = CardPrintRepository(session)

    def overview(self) -> OverviewStats:
        return OverviewStats(
            cards=self._cards.count_playable(),
            copies=self._copies.count_all(),
            unassigned_copies=self._copies.count_unassigned(),
            decks=self._decks.count_all(),
            armed_decks=self._decks.count_armed(),
            deck_cards=self._decks.count_deck_cards(),
            assignments=self._copies.count_assignments(),
        )

    def list_cards(self, search: str = "") -> list[CardSummary]:
        copy_counts = self._copies.counts_by_card()
        return [
            CardSummary(
                oracle_id=card.oracle_id,
                name=card.name,
                type_line=card.type_line,
                cmc=card.cmc,
                color_identity=card.color_identity,
                is_basic_land=card.is_basic_land,
                is_token=card.is_token,
                copy_count=copy_counts.get(card.oracle_id, 0),
                commander_legality=card.commander_legality,
            )
            for card in self._cards.list_playable(search)
        ]

    def list_inventory(
        self, *, include_editions: bool = False
    ) -> list[InventorySummaryRow]:
        edition_counts = self._copies.edition_counts() if include_editions else {}
        raw_rows = list(self._decks.inventory_copy_rows())
        assigned_counts = self._copies.assigned_counts()
        decks_by_card = self._decks.assignment_decks_by_card()
        print_rarities: dict[tuple[str, str], str | None] = {}
        if include_editions and raw_rows:
            print_rarities = self._prints.rarities_by_card_set(
                oracle_id for oracle_id, *_rest in raw_rows
            )
        summaries: list[InventorySummaryRow] = []
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
        ) in raw_rows:
            editions = _sorted_editions(edition_counts.get(oracle_id, {}))
            assigned_count = assigned_counts.get(oracle_id, 0)
            deck_entries = decks_by_card.get(oracle_id, ())
            summaries.append(
                InventorySummaryRow(
                    oracle_id=oracle_id,
                    card_name=name,
                    total_copies=total,
                    free_copies=total - assigned_count,
                    assigned_decks=tuple(deck_name for _id, deck_name in deck_entries),
                    color_identity=color_identity,
                    editions=editions,
                    type_line=type_line,
                    colors=colors,
                    cmc=cmc,
                    mana_cost=mana_cost,
                    rarity=rarity,
                    rarities=_effective_rarities(
                        rarity,
                        editions,
                        include_editions=include_editions,
                        print_rarities=print_rarities,
                        oracle_id=oracle_id,
                    ),
                    oracle_text=oracle_text,
                    commander_legality=commander_legality,
                    is_basic_land=is_basic_land,
                    is_token=is_token,
                    assigned_deck_ids=frozenset(
                        deck_id for deck_id, _name in deck_entries
                    ),
                )
            )
        return summaries

    def scryfall_status(self) -> BulkSyncStatus:
        return ScryfallBulkService(self._session).status()
