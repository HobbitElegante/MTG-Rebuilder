from mtg_rebuilder.algorithms.inventory_filters import (
    CmcCondition,
    ColorMode,
    FilterChip,
    FilterChipKind,
    InventoryFilterState,
)
from mtg_rebuilder.i18n import Translator
from mtg_rebuilder.services.browse_service import InventorySummaryRow
from mtg_rebuilder.ui.inventory_display import (
    format_color_identity,
    format_filter_button_label,
    format_filter_chip_label,
    format_filter_chips,
    format_inventory_decks,
    format_mana_cost,
    format_rarity_summary,
    mana_cost_sort_key,
    rarity_sort_rank,
)


def _row(
    *,
    free: int = 0,
    total: int = 1,
    decks: tuple[str, ...] = (),
    color_identity: str | None = None,
    rarity: str | None = None,
    rarities: frozenset[str] = frozenset(),
    cmc: float | None = None,
    mana_cost: str | None = None,
) -> InventorySummaryRow:
    return InventorySummaryRow(
        oracle_id="oid",
        card_name="Sol Ring",
        total_copies=total,
        free_copies=free,
        assigned_decks=decks,
        color_identity=color_identity,
        rarity=rarity,
        rarities=rarities or (frozenset({rarity}) if rarity else frozenset()),
        cmc=cmc,
        mana_cost=mana_cost,
    )


def test_format_inventory_decks_empty() -> None:
    translator = Translator("en")
    assert format_inventory_decks(_row(free=2, total=2), translator) == "—"


def test_format_inventory_decks_lists_names_only() -> None:
    translator = Translator("en")
    text = format_inventory_decks(
        _row(free=1, total=3, decks=("Kellan", "Athreos")),
        translator,
    )
    assert text == "Kellan, Athreos"
    assert "free" not in text.casefold()
    assert "1" not in text


def test_format_inventory_decks_spanish_placeholder() -> None:
    translator = Translator("es")
    assert format_inventory_decks(_row(free=1, total=1), translator) == "—"


def test_filter_button_counts_instead_of_ticking() -> None:
    translator = Translator("en")
    assert format_filter_button_label(InventoryFilterState(), translator) == "Filter"
    state = InventoryFilterState(
        only_with_free=True, types=frozenset({"Land", "Creature"})
    )
    assert format_filter_button_label(state, translator) == "Filter (3)"


def test_filter_button_label_is_translated() -> None:
    state = InventoryFilterState(only_with_free=True)
    assert format_filter_button_label(state, Translator("es")) == "Filtrar (1)"


def test_chip_labels_name_what_they_filter() -> None:
    translator = Translator("en")
    state = InventoryFilterState(
        only_with_free=True,
        types=frozenset({"Creature"}),
        subtypes=frozenset({"Elf"}),
        exclude_any_armed=True,
        exclude_deck_ids=frozenset({7}),
        rarities=frozenset({"M"}),
        cmc_conditions=(CmcCondition("<=", 2),),
    )
    labels = [
        label
        for _chip, label in format_filter_chips(state, translator, {7: "Kellan"})
    ]
    assert labels == [
        "With free copies",
        "Type: Creature",
        "Subtype: Elf",
        "Not in armed decks",
        "Not in: Kellan",
        "Rarity: M",
        "MV <= 2",
    ]


def test_unknown_deck_id_falls_back_to_the_raw_value() -> None:
    translator = Translator("en")
    state = InventoryFilterState(exclude_deck_ids=frozenset({99}))
    labels = [label for _chip, label in format_filter_chips(state, translator)]
    assert labels == ["Not in: 99"]


def test_color_chip_shows_the_mode_and_wubrg_order() -> None:
    translator = Translator("en")
    colors = frozenset({"G", "W"})
    chip = FilterChip(FilterChipKind.COLORS)
    expected = {
        ColorMode.AT_MOST: "Colors ≤ WG",
        ColorMode.EXACT: "Colors = WG",
        ColorMode.AT_LEAST: "Colors ≥ WG",
    }
    for mode, label in expected.items():
        state = InventoryFilterState(colors=colors, color_mode=mode)
        assert format_filter_chip_label(chip, state, translator) == label


def test_colorless_chip_replaces_the_color_chip() -> None:
    translator = Translator("en")
    state = InventoryFilterState(only_colorless=True, colors=frozenset({"R"}))
    labels = [label for _chip, label in format_filter_chips(state, translator)]
    assert labels == ["Colorless"]


def test_format_color_identity_wubrg() -> None:
    translator = Translator("en")
    assert format_color_identity("WUB", translator) == "WUB"


def test_format_color_identity_empty() -> None:
    translator = Translator("en")
    assert format_color_identity(None, translator) == "—"
    assert format_color_identity("", translator) == "—"


def test_format_mana_cost_drops_braces() -> None:
    translator = Translator("en")
    assert format_mana_cost("{2}{W/U}{R}", translator) == "2 W/U R"
    assert format_mana_cost("{u/w}", translator) == "W/U"
    # Lands print no cost, and unsynced cards have none yet.
    assert format_mana_cost("", translator) == "—"
    assert format_mana_cost(None, translator) == "—"


def test_mana_cost_sort_key_orders_by_value_then_cost() -> None:
    cheap = _row(cmc=1, mana_cost="{W}")
    mid_w = _row(cmc=2, mana_cost="{1}{W}")
    mid_u = _row(cmc=2, mana_cost="{1}{U}")
    land = _row(cmc=0, mana_cost="")
    assert mana_cost_sort_key(land) < mana_cost_sort_key(cheap)
    assert mana_cost_sort_key(cheap) < mana_cost_sort_key(mid_u)
    # Same mana value: the printed cost breaks the tie, so colors group.
    assert mana_cost_sort_key(mid_u) < mana_cost_sort_key(mid_w)


def test_format_rarity_summary_letters() -> None:
    translator = Translator("en")
    assert format_rarity_summary(_row(rarity="common"), translator) == "C"
    assert format_rarity_summary(_row(rarity="mythic"), translator) == "M"
    assert format_rarity_summary(_row(), translator) == "—"
    assert (
        format_rarity_summary(
            _row(rarities=frozenset({"mythic", "common"})), translator
        )
        == "C, M"
    )


def test_rarity_sort_rank_curm_order() -> None:
    assert rarity_sort_rank(_row(rarity="common")) < rarity_sort_rank(
        _row(rarity="uncommon")
    )
    assert rarity_sort_rank(_row(rarity="uncommon")) < rarity_sort_rank(
        _row(rarity="rare")
    )
    assert rarity_sort_rank(_row(rarity="rare")) < rarity_sort_rank(
        _row(rarity="mythic")
    )
    # Mixed: sort by lowest rarity present (C before M).
    assert rarity_sort_rank(
        _row(rarities=frozenset({"mythic", "common"}))
    ) == rarity_sort_rank(_row(rarity="common"))
