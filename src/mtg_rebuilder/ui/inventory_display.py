from mtg_rebuilder.algorithms.card_utils import is_commander_legality_issue
from mtg_rebuilder.algorithms.commander_rules import CommanderRuleIssue, CommanderRuleKind
from mtg_rebuilder.algorithms.inventory_filters import (
    RARITY_BY_CODE,
    CmcAddResolution,
    CmcAddStatus,
    CmcSetIssue,
    ColorMode,
    FilterChip,
    FilterChipKind,
    InventoryFilterState,
    active_filter_count,
    filter_chips,
    sorted_color_letters,
    sorted_rarity_codes,
)
from mtg_rebuilder.config import UNSPECIFIED_EDITION_LABEL
from mtg_rebuilder.i18n import Translator
from mtg_rebuilder.services.browse_service import InventorySummaryRow
from mtg_rebuilder.services.deck_service import CommanderLegalityIssue

# Display letters for Scryfall rarities (filter uses C/U/R/M only).
_RARITY_LETTER: dict[str, str] = {name: code for code, name in RARITY_BY_CODE.items()}
_RARITY_LETTER.update({"special": "S", "bonus": "B"})

# Ascending inventory sort: C → U → R → M (then special/bonus/unknown).
_RARITY_SORT_RANK: dict[str, int] = {
    "common": 0,
    "uncommon": 1,
    "rare": 2,
    "mythic": 3,
    "special": 4,
    "bonus": 5,
}
_UNKNOWN_RARITY_RANK = 6


def format_mana_value(cmc: float | None, translator: Translator) -> str:
    """Numeric mana value (CMC). Whole numbers as integers (GGG → 3)."""
    if cmc is None:
        return translator.t("inventory.table.colorless")
    value = float(cmc)
    if value.is_integer():
        return str(int(value))
    return f"{value:g}"


def format_color_identity(
    color_identity: str | None, translator: Translator
) -> str:
    """WUBRG string from Scryfall, or an empty-state placeholder."""
    if not color_identity:
        return translator.t("inventory.table.colorless")
    return color_identity


def _row_rarities(row: InventorySummaryRow) -> frozenset[str]:
    if row.rarities:
        return row.rarities
    if row.rarity:
        return frozenset({row.rarity})
    return frozenset()


def format_rarity_summary(row: InventorySummaryRow, translator: Translator) -> str:
    """C/U/R/M letter(s) for the row; mixed rarities listed in CURM order."""
    rarities = _row_rarities(row)
    if not rarities:
        return translator.t("inventory.table.colorless")
    ordered = sorted(
        rarities, key=lambda name: _RARITY_SORT_RANK.get(name, _UNKNOWN_RARITY_RANK)
    )
    letters = [_RARITY_LETTER.get(name, "?") for name in ordered]
    if len(letters) == 1:
        return letters[0]
    return ", ".join(letters)


def rarity_sort_rank(row: InventorySummaryRow) -> int:
    """Sort key for rarity: lower = earlier in C→U→R→M."""
    rarities = _row_rarities(row)
    if not rarities:
        return _UNKNOWN_RARITY_RANK
    return min(_RARITY_SORT_RANK.get(name, _UNKNOWN_RARITY_RANK) for name in rarities)


def format_edition_summary(row: InventorySummaryRow) -> str:
    """One set code when they all match, otherwise a per-edition breakdown."""
    if not row.editions:
        return UNSPECIFIED_EDITION_LABEL
    if len(row.editions) == 1:
        code, _ = row.editions[0]
        return code or UNSPECIFIED_EDITION_LABEL
    return ", ".join(
        f"{code or UNSPECIFIED_EDITION_LABEL} x{count}" for code, count in row.editions
    )


def format_inventory_decks(row: InventorySummaryRow, translator: Translator) -> str:
    """Deck names that hold assigned copies, or an empty-state placeholder."""
    if not row.assigned_decks:
        return translator.t("inventory.table.no_decks")
    return ", ".join(row.assigned_decks)


def format_inventory_detail_lines(
    row: InventorySummaryRow,
    translator: Translator,
    *,
    track_editions: bool,
) -> list[tuple[str, str]]:
    """Label/value pairs for the Inventory preview details list."""
    assigned = row.total_copies - row.free_copies
    lines: list[tuple[str, str]] = [
        (translator.t("browse.cards.name"), row.card_name),
        (translator.t("inventory.table.cmc"), format_mana_value(row.cmc, translator)),
        (
            translator.t("inventory.table.color"),
            format_color_identity(row.color_identity, translator),
        ),
        (
            translator.t("inventory.table.rarity"),
            format_rarity_summary(row, translator),
        ),
    ]
    if track_editions:
        lines.append(
            (translator.t("inventory.table.edition"), format_edition_summary(row))
        )
    lines.extend(
        [
            (translator.t("inventory.table.total"), str(row.total_copies)),
            (translator.t("inventory.table.free"), str(row.free_copies)),
            (translator.t("inventory.table.assigned"), str(assigned)),
            (
                translator.t("inventory.table.decks"),
                format_inventory_decks(row, translator),
            ),
        ]
    )
    return lines


def format_inventory_assigned(row: InventorySummaryRow, translator: Translator) -> str:
    """Legacy mixed cell (kept for tests / callers that still need the blend)."""
    if row.free_copies == row.total_copies:
        return translator.t("browse.inventory.free")
    if row.free_copies == 0:
        return ", ".join(row.assigned_decks)
    if not row.assigned_decks:
        return translator.t("browse.inventory.free")
    return translator.t("browse.inventory.mixed").format(
        free=row.free_copies,
        decks=", ".join(row.assigned_decks),
    )


def format_availability_status(row: InventorySummaryRow, translator: Translator) -> str:
    if row.free_copies > 0:
        return translator.t("inventory.status.available").format(count=row.free_copies)
    return translator.t("inventory.status.unavailable").format(count=row.total_copies)


_COLOR_MODE_CHIP_KEY: dict[ColorMode, str] = {
    ColorMode.AT_MOST: "inventory.filters.chip.colors_at_most",
    ColorMode.EXACT: "inventory.filters.chip.colors_exact",
    ColorMode.AT_LEAST: "inventory.filters.chip.colors_at_least",
}


def format_filter_button_label(
    state: InventoryFilterState, translator: Translator
) -> str:
    """``Filter`` when idle, ``Filter (3)`` when three filters are on."""
    count = active_filter_count(state)
    if not count:
        return translator.t("inventory.filters.toggle")
    return translator.t("inventory.filters.toggle_count").format(count=count)


def format_cmc_hint(
    add: CmcAddResolution,
    set_issue: CmcSetIssue,
    op: str,
    value: float,
    translator: Translator,
) -> str:
    """Why CMC *Add* is disabled, or a warning about the committed rows."""
    display = int(value) if float(value).is_integer() else value
    if add.status is CmcAddStatus.DUPLICATE:
        return translator.t("inventory.filters.cmc_duplicate").format(
            op=op, value=display
        )
    if add.status is CmcAddStatus.CONFLICT:
        return translator.t("inventory.filters.cmc_conflict").format(
            op=op, value=display
        )
    if set_issue is CmcSetIssue.DUPLICATE:
        return translator.t("inventory.filters.cmc_duplicates")
    if set_issue is CmcSetIssue.IMPOSSIBLE:
        return translator.t("inventory.filters.cmc_impossible")
    return ""


def format_filter_chip_label(
    chip: FilterChip,
    state: InventoryFilterState,
    translator: Translator,
    deck_names: dict[int, str] | None = None,
) -> str:
    t = translator.t
    if chip.kind is FilterChipKind.ONLY_FREE:
        return t("inventory.filters.chip.only_free")
    if chip.kind is FilterChipKind.TYPE:
        return t("inventory.filters.chip.type").format(name=chip.value)
    if chip.kind is FilterChipKind.SUBTYPE:
        return t("inventory.filters.chip.subtype").format(name=chip.value)
    if chip.kind is FilterChipKind.ANY_ARMED:
        return t("inventory.filters.chip.any_armed")
    if chip.kind is FilterChipKind.DECK:
        names = deck_names or {}
        deck_id = int(chip.value)
        return t("inventory.filters.chip.deck").format(
            name=names.get(deck_id, chip.value)
        )
    if chip.kind is FilterChipKind.COLORLESS:
        return t("inventory.filters.chip.colorless")
    if chip.kind is FilterChipKind.COLORS:
        key = _COLOR_MODE_CHIP_KEY.get(
            state.color_mode, _COLOR_MODE_CHIP_KEY[ColorMode.AT_MOST]
        )
        return t(key).format(colors="".join(sorted_color_letters(state.colors)))
    if chip.kind is FilterChipKind.RARITY:
        return t("inventory.filters.chip.rarity").format(
            codes=", ".join(sorted_rarity_codes(state.rarities))
        )
    condition = state.cmc_conditions[int(chip.value)]
    return t("inventory.filters.chip.cmc").format(
        op=condition.op, value=format_mana_value(condition.value, translator)
    )


def format_filter_chips(
    state: InventoryFilterState,
    translator: Translator,
    deck_names: dict[int, str] | None = None,
) -> list[tuple[FilterChip, str]]:
    """Every active filter paired with its chip label, in dialog order."""
    return [
        (chip, format_filter_chip_label(chip, state, translator, deck_names))
        for chip in filter_chips(state)
    ]


def format_commander_legality_label(legality: str, translator: Translator) -> str:
    key = f"decks.legality.{legality.casefold()}"
    label = translator.t(key)
    # Translator returns the key itself when missing in some setups; fall back.
    if label == key:
        return legality
    return label


def format_commander_legality_tooltip(
    issues: list[CommanderLegalityIssue], translator: Translator
) -> str:
    if not issues:
        return ""
    header = translator.t("decks.legality.tooltip_header")
    lines = [
        translator.t("decks.legality.tooltip_line").format(
            name=issue.name,
            status=format_commander_legality_label(issue.legality, translator),
        )
        for issue in issues
    ]
    return header + "\n" + "\n".join(lines)


def format_commander_rules_tooltip(
    issues: list[CommanderRuleIssue], translator: Translator
) -> str:
    if not issues:
        return ""
    colorless = translator.t("decks.rules.colorless")
    lines = []
    for issue in issues:
        if issue.kind is CommanderRuleKind.COLOR_IDENTITY:
            lines.append(
                translator.t("decks.rules.color_identity").format(
                    name=issue.name,
                    colors=issue.colors or colorless,
                    allowed=issue.allowed or colorless,
                )
            )
        elif issue.kind is CommanderRuleKind.PAIRING:
            lines.append(
                translator.t("decks.rules.pairing").format(
                    name=issue.name,
                    commander=issue.commander,
                )
            )
        elif issue.kind is CommanderRuleKind.SINGLETON:
            lines.append(
                translator.t("decks.rules.singleton").format(
                    name=issue.name,
                    qty=issue.quantity,
                    limit=issue.allowed or "1",
                )
            )
        elif issue.kind is CommanderRuleKind.DECK_SIZE:
            lines.append(
                translator.t("decks.rules.deck_size").format(
                    count=issue.name,
                    expected=issue.allowed or "100",
                )
            )
        else:
            lines.append(
                translator.t("decks.rules.missing_data").format(name=issue.name)
            )
    header = translator.t("decks.rules.tooltip_header")
    return header + "\n" + "\n".join(lines)


def format_deck_warning_tooltip(
    legality_issues: list[CommanderLegalityIssue],
    rule_issues: list[CommanderRuleIssue],
    translator: Translator,
) -> str:
    """Both advisory checks share one ⚠, so their tooltips are stacked."""
    blocks = [
        format_commander_legality_tooltip(legality_issues, translator),
        format_commander_rules_tooltip(rule_issues, translator),
    ]
    return "\n\n".join(block for block in blocks if block)


def format_card_legality_tooltip(
    name: str, legality: str | None, translator: Translator
) -> str:
    if not is_commander_legality_issue(legality):
        return ""
    assert legality is not None
    return translator.t("decks.legality.card_tooltip").format(
        name=name,
        status=format_commander_legality_label(legality, translator),
    )
