"""Pure helpers for the deck detail card list: sort and group-by-type (no Qt).

Command-zone cards (commander / partner / companion / background) stay pinned
ahead of the main list regardless of the chosen sort, matching how the list
always displayed them. Multi-faced cards classify by their front face, like
the deck statistics do.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from mtg_rebuilder.algorithms.deck_stats import TYPE_ORDER
from mtg_rebuilder.i18n import Translator
from mtg_rebuilder.models.enums import DeckCardRole
from mtg_rebuilder.services.deck_service import CardListStock

if TYPE_CHECKING:
    from mtg_rebuilder.services.deck_service import DeckCardSummary

DeckCardsSortKey = Literal["mana_value", "alphabetical"]

# Group ids in display order; "command" and empty groups are skipped as needed.
COMMAND_GROUP = "command"
LAND_GROUP = "Land"
OTHER_GROUP = "Other"
CARD_TYPE_GROUP_ORDER = (*TYPE_ORDER, LAND_GROUP, OTHER_GROUP)

_ROLE_PRIORITY = {
    DeckCardRole.COMMANDER: 0,
    DeckCardRole.PARTNER: 1,
    DeckCardRole.COMPANION: 2,
    DeckCardRole.BACKGROUND: 3,
}


def _front_face(type_line: str | None) -> str | None:
    if type_line is None:
        return None
    return type_line.split(" // ", 1)[0]


def primary_card_type(type_line: str | None) -> str:
    """Single bucket per card: lands first, then TYPE_ORDER precedence."""
    front = _front_face(type_line)
    if not front:
        return OTHER_GROUP
    if "Land" in front:
        return LAND_GROUP
    for type_name in TYPE_ORDER:
        if type_name in front:
            return type_name
    return OTHER_GROUP


def _split_command_zone(
    cards: list[DeckCardSummary],
) -> tuple[list[DeckCardSummary], list[DeckCardSummary]]:
    zone = sorted(
        (card for card in cards if card.role in _ROLE_PRIORITY),
        key=lambda card: (_ROLE_PRIORITY[card.role], card.name.casefold()),
    )
    main = [card for card in cards if card.role not in _ROLE_PRIORITY]
    return zone, main


def _sorted_main(
    cards: list[DeckCardSummary],
    *,
    key: DeckCardsSortKey,
    ascending: bool,
) -> list[DeckCardSummary]:
    if key == "mana_value":
        # Names always read A→Z inside a mana-value tie, in both directions.
        by_name = sorted(cards, key=lambda card: card.name.casefold())
        return sorted(
            by_name,
            key=lambda card: card.cmc if card.cmc is not None else 0.0,
            reverse=not ascending,
        )
    return sorted(
        cards,
        key=lambda card: card.name.casefold(),
        reverse=not ascending,
    )


def sort_deck_cards(
    cards: list[DeckCardSummary],
    *,
    key: DeckCardsSortKey,
    ascending: bool,
) -> list[DeckCardSummary]:
    """Flat list: command zone pinned first, then the main cards sorted."""
    zone, main = _split_command_zone(cards)
    return zone + _sorted_main(main, key=key, ascending=ascending)


def group_deck_cards(
    cards: list[DeckCardSummary],
    *,
    key: DeckCardsSortKey,
    ascending: bool,
) -> list[tuple[str, list[DeckCardSummary]]]:
    """(group id, sorted cards) pairs; command zone first, empty groups out."""
    zone, main = _split_command_zone(cards)
    groups: list[tuple[str, list[DeckCardSummary]]] = []
    if zone:
        groups.append((COMMAND_GROUP, zone))
    buckets: dict[str, list[DeckCardSummary]] = {}
    for card in main:
        buckets.setdefault(primary_card_type(card.type_line), []).append(card)
    for group in CARD_TYPE_GROUP_ORDER:
        if group in buckets:
            groups.append(
                (group, _sorted_main(buckets[group], key=key, ascending=ascending))
            )
    return groups


def format_card_stock_text(
    stock: CardListStock,
    translator: Translator,
    *,
    is_basic_land: bool,
) -> str:
    """Three lines for the selected-card column: inventory, free, lists.

    Basics are unlimited and are not stored as copies, so the first two
    lines use the unlimited label instead of a zero that would look missing.
    """
    if is_basic_land:
        inventory = translator.t("decks.cards.stock.unlimited")
        free = inventory
    else:
        inventory = str(stock.total_copies)
        free = str(stock.free_copies)
    return "\n".join(
        (
            translator.t("decks.cards.stock.inventory").format(count=inventory),
            translator.t("decks.cards.stock.free").format(count=free),
            translator.t("decks.cards.stock.decks").format(count=stock.decks_using),
        )
    )
