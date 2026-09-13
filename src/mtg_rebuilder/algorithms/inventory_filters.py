"""Local inventory panel filters (type / subtype / color / rarity / mana value / decks).

Independent of Scryfall syntax. Color identity is compared through a
``ColorMode``: at most (Scryfall ``id<=``), exactly, or at least the checked
letters. "At most" with all five checked keeps everything, so it counts as no
filter; the other two modes are meaningful with any non-empty selection. An
empty selection never means "colorless" — that is the separate
``only_colorless`` flag, because otherwise the empty identity would be
unreachable.

Types and subtypes are two separate groups: OR inside each one, AND between
them, so ``Creature`` + ``Elf`` means "elf creatures". Subtypes are whatever
follows the em dash of a type line, tokenized by word — good enough for the
single-word types that cover almost every card.

Rarity uses Scryfall print rarities (``common`` / ``uncommon`` / ``rare`` /
``mythic``). UI letters C/U/R/M; empty or all four = no filter. Match is OR
across selected rarities. ``special`` / ``bonus`` are not offered in the UI.

Deck exclusion uses physical assignments (``CardAssignment``): hide cards that
have a copy assigned to any armed deck, or to selected deck ids.

``filter_chips`` breaks an active state into individually removable pieces so
the UI can show them above the table and drop them one by one.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
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


class ColorMode(StrEnum):
    """How the checked WUBRG letters are compared against a card's identity."""

    AT_MOST = "at_most"
    EXACT = "exact"
    AT_LEAST = "at_least"


COLOR_MODES: tuple[ColorMode, ...] = (
    ColorMode.AT_MOST,
    ColorMode.EXACT,
    ColorMode.AT_LEAST,
)

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
    # Subset of WUBRG, compared through `color_mode`.
    colors: frozenset[str] = frozenset()
    color_mode: ColorMode = ColorMode.AT_MOST
    # Keep only cards with an empty color identity; overrides `colors`.
    only_colorless: bool = False
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
        """Whether the WUBRG selection narrows anything, given the mode."""
        if self.only_colorless or not self.colors:
            return False
        if self.color_mode is ColorMode.AT_MOST:
            # "At most all five colors" keeps every card.
            return self.colors != frozenset(WUBRG)
        return True

    @property
    def rarity_filter_active(self) -> bool:
        return bool(self.rarities) and self.rarities != frozenset(RARITY_CODES)

    @property
    def is_active(self) -> bool:
        return (
            bool(self.types)
            or bool(self.subtypes)
            or self.only_colorless
            or self.color_filter_active
            or self.rarity_filter_active
            or bool(self.cmc_conditions)
            or self.exclude_any_armed
            or bool(self.exclude_deck_ids)
            or self.only_with_free
        )


class FilterChipKind(StrEnum):
    """One removable piece of an active filter state."""

    ONLY_FREE = "only_free"
    TYPE = "type"
    SUBTYPE = "subtype"
    ANY_ARMED = "any_armed"
    DECK = "deck"
    COLORS = "colors"
    COLORLESS = "colorless"
    RARITY = "rarity"
    CMC = "cmc"


@dataclass(frozen=True)
class FilterChip:
    """``value`` identifies the chip inside its kind (type name, deck id, …)."""

    kind: FilterChipKind
    value: str = ""


def filter_chips(state: InventoryFilterState) -> tuple[FilterChip, ...]:
    """Active filters as individually removable chips, in dialog order.

    Colors and rarity are one chip each: the mode applies to the whole group,
    so dropping a single letter would not be a well-defined action.
    """
    chips: list[FilterChip] = []
    if state.only_with_free:
        chips.append(FilterChip(FilterChipKind.ONLY_FREE))
    chips.extend(
        FilterChip(FilterChipKind.TYPE, name) for name in sorted(state.types)
    )
    chips.extend(
        FilterChip(FilterChipKind.SUBTYPE, name) for name in sorted(state.subtypes)
    )
    if state.exclude_any_armed:
        chips.append(FilterChip(FilterChipKind.ANY_ARMED))
    chips.extend(
        FilterChip(FilterChipKind.DECK, str(deck_id))
        for deck_id in sorted(state.exclude_deck_ids)
    )
    if state.only_colorless:
        chips.append(FilterChip(FilterChipKind.COLORLESS))
    elif state.color_filter_active:
        chips.append(FilterChip(FilterChipKind.COLORS))
    if state.rarity_filter_active:
        chips.append(FilterChip(FilterChipKind.RARITY))
    chips.extend(
        FilterChip(FilterChipKind.CMC, str(index))
        for index in range(len(state.cmc_conditions))
    )
    return tuple(chips)


def active_filter_count(state: InventoryFilterState) -> int:
    return len(filter_chips(state))


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


# Domain of the filter spin (0–99). Enough to decide AND-satisfiability for UI ops.
CMC_FILTER_DOMAIN: range = range(0, 100)


class CmcAddStatus(StrEnum):
    """Whether the draft row can be appended to the active CMC list."""

    OK = "ok"
    DUPLICATE = "duplicate"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class CmcAddResolution:
    status: CmcAddStatus

    @property
    def can_add(self) -> bool:
        return self.status is CmcAddStatus.OK


class CmcSetIssue(StrEnum):
    """Problems already present among the committed CMC rows."""

    NONE = "none"
    DUPLICATE = "duplicate"
    IMPOSSIBLE = "impossible"


def has_duplicate_cmc_conditions(conditions: Sequence[CmcCondition]) -> bool:
    seen: set[tuple[str, float]] = set()
    for condition in conditions:
        key = (condition.op, float(condition.value))
        if key in seen:
            return True
        seen.add(key)
    return False


def cmc_conditions_satisfiable(conditions: Sequence[CmcCondition]) -> bool:
    """True if some integer mana value in the filter domain matches every condition."""
    if not conditions:
        return True
    return any(
        all(matches_cmc(float(value), condition) for condition in conditions)
        for value in CMC_FILTER_DOMAIN
    )


def cmc_conditions_issue(conditions: Sequence[CmcCondition]) -> CmcSetIssue:
    if has_duplicate_cmc_conditions(conditions):
        return CmcSetIssue.DUPLICATE
    if conditions and not cmc_conditions_satisfiable(conditions):
        return CmcSetIssue.IMPOSSIBLE
    return CmcSetIssue.NONE


def resolve_cmc_add(
    existing: Sequence[CmcCondition], op: str, value: float
) -> CmcAddResolution:
    """Decide if appending ``op``/``value`` is redundant or would empty the result."""
    proposed = CmcCondition(op, float(value))
    if any(
        condition.op == proposed.op and float(condition.value) == proposed.value
        for condition in existing
    ):
        return CmcAddResolution(CmcAddStatus.DUPLICATE)
    if not cmc_conditions_satisfiable((*existing, proposed)):
        return CmcAddResolution(CmcAddStatus.CONFLICT)
    return CmcAddResolution(CmcAddStatus.OK)


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


def matches_color_identity_exact(
    color_identity: str | None, wanted: frozenset[str]
) -> bool:
    """``id=``: the identity is exactly ``wanted``."""
    return color_identity_letters(color_identity) == wanted


def matches_color_identity_at_least(
    color_identity: str | None, required: frozenset[str]
) -> bool:
    """``id>=``: the identity contains every color in ``required``."""
    return color_identity_letters(color_identity) >= required


def matches_color_identity(
    color_identity: str | None, selected: frozenset[str], mode: ColorMode
) -> bool:
    if mode is ColorMode.EXACT:
        return matches_color_identity_exact(color_identity, selected)
    if mode is ColorMode.AT_LEAST:
        return matches_color_identity_at_least(color_identity, selected)
    return matches_color_identity_at_most(color_identity, selected)


def is_colorless(color_identity: str | None) -> bool:
    return not color_identity_letters(color_identity)


def sorted_color_letters(colors: frozenset[str]) -> tuple[str, ...]:
    """Selected letters in WUBRG order, for labels."""
    return tuple(letter for letter in WUBRG if letter in colors)


def sorted_rarity_codes(codes: frozenset[str]) -> tuple[str, ...]:
    """Selected rarity codes in C→U→R→M order, for labels."""
    return tuple(code for code in RARITY_CODES if code in codes)


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
    if state.only_colorless and not is_colorless(card.color_identity):
        return False
    if state.color_filter_active:
        if not matches_color_identity(
            card.color_identity, state.colors, state.color_mode
        ):
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
