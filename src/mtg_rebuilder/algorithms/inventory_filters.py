"""Local inventory panel filters (type / subtype / color / rarity / mana value / decks).

Independent of Scryfall syntax. Color identity uses Scryfall ``id<=`` semantics:
at most the selected colors (colorless included). Zero or all five color
checkboxes means no color filter.

Types and subtypes are two separate groups: OR inside each one, AND between
them, so ``Creature`` + ``Elf`` means "elf creatures". Subtypes are whatever
follows the em dash of a type line, tokenized by word — good enough for the
single-word types that cover almost every card.

Rarity uses Scryfall print rarities (``common`` / ``uncommon`` / ``rare`` /
``mythic``). UI letters C/U/R/M; empty or all four = no filter. Match is OR
across selected rarities. ``special`` / ``bonus`` are not offered in the UI.

Deck exclusion uses physical assignments (``CardAssignment``): hide cards that
have a copy assigned to any armed deck, or to selected deck ids.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

WUBRG = ("W", "U", "B", "R", "G")

# Filter UI codes → Scryfall rarity strings.
RARITY_CODES = ("C", "U", "R", "M")
RARITY_BY_CODE: dict[str, str] = {
    "C": "common",
    "U": "uncommon",
    "R": "rare",
    "M": "mythic",
}

# Card types / common type-line tokens offered in the type picker.
CARD_TYPE_OPTIONS: tuple[str, ...] = (
    "Artifact",
    "Battle",
    "Creature",
    "Enchantment",
    "Instant",
    "Land",
    "Planeswalker",
    "Sorcery",
    "Kindred",
    "Legendary",
    "Snow",
    "Basic",
)

CMC_OPS: tuple[str, ...] = ("=", "!=", "<", "<=", ">", ">=")

# Type lines separate supertypes/types from subtypes with an em dash; a few
# sources use the en dash or a plain hyphen instead.
_SUBTYPE_SEPARATORS = ("—", "–", " - ")
_FACE_SEPARATOR = "//"


class FilterableCard(Protocol):
    oracle_id: str
    card_name: str
    type_line: str | None
    color_identity: str | None
    cmc: float | None
    rarities: frozenset[str]
    assigned_deck_ids: frozenset[int]
    free_copies: int


@dataclass(frozen=True)
class CmcCondition:
    op: str
    value: float


@dataclass(frozen=True)
class InventoryFilterState:
    """Active panel filters. Empty collections / inactive color set = no filter."""

    types: frozenset[str] = frozenset()
    # Subtypes (past the em dash). OR between them, AND against `types`.
    subtypes: frozenset[str] = frozenset()
    # Subset of WUBRG. Empty or all five → no color filter.
    colors: frozenset[str] = frozenset()
    # Subset of RARITY_CODES (C/U/R/M). Empty or all four → no rarity filter.
    rarities: frozenset[str] = frozenset()
    cmc_conditions: tuple[CmcCondition, ...] = ()
    # Hide cards with any physical assignment to an armed deck.
    exclude_any_armed: bool = False
    # Hide cards with a physical assignment to any of these deck ids.
    exclude_deck_ids: frozenset[int] = frozenset()
    # Keep only cards with at least one unassigned (free) copy.
    only_with_free: bool = False

    @property
    def color_filter_active(self) -> bool:
        return bool(self.colors) and self.colors != frozenset(WUBRG)

    @property
    def rarity_filter_active(self) -> bool:
        return bool(self.rarities) and self.rarities != frozenset(RARITY_CODES)

    @property
    def is_active(self) -> bool:
        return (
            bool(self.types)
            or bool(self.subtypes)
            or self.color_filter_active
            or self.rarity_filter_active
            or bool(self.cmc_conditions)
            or self.exclude_any_armed
            or bool(self.exclude_deck_ids)
            or self.only_with_free
        )


def color_identity_letters(color_identity: str | None) -> frozenset[str]:
    if not color_identity:
        return frozenset()
    return frozenset(letter for letter in color_identity.upper() if letter in WUBRG)


def rarities_for_codes(codes: frozenset[str]) -> frozenset[str]:
    return frozenset(
        RARITY_BY_CODE[code] for code in codes if code in RARITY_BY_CODE
    )


def matches_cmc(card_cmc: float | None, condition: CmcCondition) -> bool:
    actual = 0.0 if card_cmc is None else float(card_cmc)
    target = condition.value
    op = condition.op
    if op == "=":
        return actual == target
    if op == "!=":
        return actual != target
    if op == "<":
        return actual < target
    if op == "<=":
        return actual <= target
    if op == ">":
        return actual > target
    if op == ">=":
        return actual >= target
    return False


def matches_type_line(type_line: str | None, selected: frozenset[str]) -> bool:
    """OR match: type_line contains any selected token (case-insensitive word)."""
    if not selected:
        return True
    haystack = (type_line or "").casefold()
    if not haystack:
        return False
    tokens = {part.strip().casefold() for part in haystack.replace("—", " ").replace("-", " ").split()}
    tokens.discard("")
    for wanted in selected:
        needle = wanted.casefold()
        if needle in tokens or needle in haystack:
            return True
    return False


def subtypes_of(type_line: str | None) -> frozenset[str]:
    """Words past the em dash, per face. ``Creature — Elf Druid`` → Elf, Druid."""
    if not type_line:
        return frozenset()
    found: set[str] = set()
    for face in type_line.split(_FACE_SEPARATOR):
        tail = ""
        for separator in _SUBTYPE_SEPARATORS:
            if separator in face:
                tail = face.split(separator, 1)[1]
                break
        for word in tail.split():
            cleaned = word.strip()
            if cleaned:
                found.add(cleaned)
    return frozenset(found)


def subtype_catalog(type_lines: Sequence[str | None]) -> tuple[str, ...]:
    """Sorted subtypes present in the collection, for the picker."""
    seen: dict[str, str] = {}
    for line in type_lines:
        for subtype in subtypes_of(line):
            seen.setdefault(subtype.casefold(), subtype)
    return tuple(sorted(seen.values(), key=str.casefold))


def matches_subtypes(type_line: str | None, selected: frozenset[str]) -> bool:
    """OR match against the card's subtypes (case-insensitive)."""
    if not selected:
        return True
    have = {subtype.casefold() for subtype in subtypes_of(type_line)}
    return any(wanted.casefold() in have for wanted in selected)


def matches_color_identity_at_most(
    color_identity: str | None, allowed: frozenset[str]
) -> bool:
    """``id<=``: every color in the identity is in ``allowed`` (colorless OK)."""
    have = color_identity_letters(color_identity)
    return have <= allowed


def matches_rarity(
    card_rarities: frozenset[str], selected_codes: frozenset[str]
) -> bool:
    """OR: any of the card's Scryfall rarities is among the selected codes."""
    wanted = rarities_for_codes(selected_codes)
    if not wanted:
        return True
    return bool(card_rarities & wanted)


def matches_panel_filters(card: FilterableCard, state: InventoryFilterState) -> bool:
    if state.types and not matches_type_line(card.type_line, state.types):
        return False
    if state.subtypes and not matches_subtypes(card.type_line, state.subtypes):
        return False
    if state.only_with_free and card.free_copies <= 0:
        return False
    if state.color_filter_active:
        if not matches_color_identity_at_most(card.color_identity, state.colors):
            return False
    if state.rarity_filter_active:
        if not matches_rarity(card.rarities, state.rarities):
            return False
    for condition in state.cmc_conditions:
        if not matches_cmc(card.cmc, condition):
            return False
    assigned = card.assigned_deck_ids
    if state.exclude_any_armed and assigned:
        return False
    if state.exclude_deck_ids and assigned & state.exclude_deck_ids:
        return False
    return True


def matches_name(card: FilterableCard, needle: str) -> bool:
    text = needle.strip().casefold()
    if not text:
        return True
    return text in card.card_name.casefold()


def filter_inventory_cards(
    rows: Sequence[FilterableCard],
    *,
    name_query: str = "",
    panel: InventoryFilterState | None = None,
    scryfall_oracle_ids: set[str] | None = None,
) -> list[FilterableCard]:
    """Apply name (optional), panel filters, and optional Scryfall id intersection."""
    state = panel or InventoryFilterState()
    result: list[FilterableCard] = []
    for row in rows:
        if scryfall_oracle_ids is not None and row.oracle_id not in scryfall_oracle_ids:
            continue
        if name_query and not matches_name(row, name_query):
            continue
        if not matches_panel_filters(row, state):
            continue
        result.append(row)
    return result
