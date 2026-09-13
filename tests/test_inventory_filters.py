"""Tests for inventory panel filters (type / subtype / colors / rarity / CMC / decks)."""

from mtg_rebuilder.algorithms.inventory_filters import (
    CmcAddStatus,
    CmcCondition,
    CmcSetIssue,
    ColorMode,
    FilterChip,
    FilterChipKind,
    InventoryFilterState,
    active_filter_count,
    cmc_conditions_issue,
    cmc_conditions_satisfiable,
    filter_chips,
    filter_inventory_cards,
    matches_color_identity_at_least,
    matches_color_identity_at_most,
    matches_color_identity_exact,
    matches_panel_filters,
    matches_rarity,
    matches_subtypes,
    matches_type_line,
    resolve_cmc_add,
    sorted_color_letters,
    sorted_rarity_codes,
    subtype_catalog,
    subtypes_of,
)
from mtg_rebuilder.services.browse_service import InventorySummaryRow


def _row(
    *,
    name: str = "Lightning Bolt",
    oracle_id: str = "bolt",
    type_line: str = "Instant",
    color_identity: str | None = "R",
    cmc: float | None = 1,
    rarity: str | None = "common",
    rarities: frozenset[str] | None = None,
    assigned_deck_ids: frozenset[int] = frozenset(),
    free_copies: int | None = None,
) -> InventorySummaryRow:
    assigned = bool(assigned_deck_ids)
    total = 1
    free = free_copies if free_copies is not None else (0 if assigned else 1)
    effective = rarities if rarities is not None else (
        frozenset({rarity}) if rarity else frozenset()
    )
    return InventorySummaryRow(
        oracle_id=oracle_id,
        card_name=name,
        total_copies=total,
        free_copies=free,
        assigned_decks=(),
        color_identity=color_identity,
        type_line=type_line,
        cmc=cmc,
        rarity=rarity,
        rarities=effective,
        assigned_deck_ids=assigned_deck_ids,
    )


def test_color_at_most_includes_subsets_and_colorless() -> None:
    allowed = frozenset({"R", "B"})
    assert matches_color_identity_at_most("R", allowed)
    assert matches_color_identity_at_most("B", allowed)
    assert matches_color_identity_at_most("RB", allowed)
    assert matches_color_identity_at_most("BR", allowed)
    assert matches_color_identity_at_most("", allowed)
    assert matches_color_identity_at_most(None, allowed)
    assert not matches_color_identity_at_most("RBG", allowed)
    assert not matches_color_identity_at_most("W", allowed)


def test_color_filter_inactive_when_empty_or_all_five() -> None:
    assert not InventoryFilterState(colors=frozenset()).color_filter_active
    assert not InventoryFilterState(
        colors=frozenset("WUBRG")
    ).color_filter_active
    assert InventoryFilterState(colors=frozenset({"R", "B"})).color_filter_active


def test_color_exact_needs_the_whole_identity() -> None:
    wanted = frozenset({"R", "B"})
    assert matches_color_identity_exact("RB", wanted)
    assert matches_color_identity_exact("BR", wanted)
    assert not matches_color_identity_exact("R", wanted)
    assert not matches_color_identity_exact("RBG", wanted)
    assert matches_color_identity_exact(None, frozenset())


def test_color_at_least_allows_extra_colors() -> None:
    required = frozenset({"R"})
    assert matches_color_identity_at_least("R", required)
    assert matches_color_identity_at_least("RG", required)
    assert not matches_color_identity_at_least("G", required)
    assert not matches_color_identity_at_least(None, required)


def test_all_five_still_filters_in_exact_and_at_least_modes() -> None:
    """Only "at most" is a no-op with the five letters checked."""
    five = frozenset("WUBRG")
    assert not InventoryFilterState(
        colors=five, color_mode=ColorMode.AT_MOST
    ).color_filter_active
    assert InventoryFilterState(
        colors=five, color_mode=ColorMode.EXACT
    ).color_filter_active
    assert InventoryFilterState(
        colors=five, color_mode=ColorMode.AT_LEAST
    ).color_filter_active


def test_panel_filter_honours_the_color_mode() -> None:
    mono = _row(name="Bolt", oracle_id="bolt", color_identity="R")
    gruul = _row(name="Gruul", oracle_id="gruul", color_identity="RG")
    selected = frozenset({"R"})

    at_most = InventoryFilterState(colors=selected, color_mode=ColorMode.AT_MOST)
    assert matches_panel_filters(mono, at_most)
    assert not matches_panel_filters(gruul, at_most)

    exact = InventoryFilterState(colors=selected, color_mode=ColorMode.EXACT)
    assert matches_panel_filters(mono, exact)
    assert not matches_panel_filters(gruul, exact)

    at_least = InventoryFilterState(colors=selected, color_mode=ColorMode.AT_LEAST)
    assert matches_panel_filters(mono, at_least)
    assert matches_panel_filters(gruul, at_least)


def test_only_colorless_reaches_the_empty_identity() -> None:
    """The unreachable state before: zero checkboxes meant "no filter"."""
    artifact = _row(name="Sol Ring", oracle_id="sol", color_identity=None)
    empty_string = _row(name="Wastes", oracle_id="wastes", color_identity="")
    red = _row(name="Bolt", oracle_id="bolt", color_identity="R")
    state = InventoryFilterState(only_colorless=True)

    assert matches_panel_filters(artifact, state)
    assert matches_panel_filters(empty_string, state)
    assert not matches_panel_filters(red, state)
    assert state.is_active


def test_only_colorless_overrides_the_letter_selection() -> None:
    red = _row(color_identity="R")
    colorless = _row(name="Sol Ring", oracle_id="sol", color_identity=None)
    state = InventoryFilterState(
        colors=frozenset({"R"}),
        color_mode=ColorMode.AT_LEAST,
        only_colorless=True,
    )
    assert not state.color_filter_active
    assert not matches_panel_filters(red, state)
    assert matches_panel_filters(colorless, state)


def test_letters_and_rarity_codes_are_sorted_for_labels() -> None:
    assert sorted_color_letters(frozenset({"G", "W", "B"})) == ("W", "B", "G")
    assert sorted_rarity_codes(frozenset({"M", "C"})) == ("C", "M")


def test_type_match_is_or_across_selected() -> None:
    assert matches_type_line("Creature — Elf Druid", frozenset({"Creature"}))
    assert matches_type_line("Legendary Creature — Human", frozenset({"Legendary"}))
    assert matches_type_line("Artifact Creature — Construct", frozenset({"Instant", "Artifact"}))
    assert not matches_type_line("Instant", frozenset({"Creature", "Sorcery"}))


def test_subtypes_are_read_past_the_dash_on_every_face() -> None:
    assert subtypes_of("Creature — Elf Druid") == frozenset({"Elf", "Druid"})
    assert subtypes_of("Legendary Artifact — Equipment") == frozenset({"Equipment"})
    assert subtypes_of("Instant") == frozenset()
    assert subtypes_of(None) == frozenset()
    assert subtypes_of("Creature — Human Wizard // Instant") == frozenset(
        {"Human", "Wizard"}
    )


def test_subtype_catalog_is_sorted_and_deduplicated() -> None:
    lines = [
        "Creature — Elf Druid",
        "Creature — elf Warrior",
        "Instant",
        None,
        "Artifact — Equipment",
    ]
    assert subtype_catalog(lines) == ("Druid", "Elf", "Equipment", "Warrior")


def test_subtype_match_is_or_and_case_insensitive() -> None:
    assert matches_subtypes("Creature — Elf Druid", frozenset({"Elf"}))
    assert matches_subtypes("Creature — Elf Druid", frozenset({"elf"}))
    assert matches_subtypes("Creature — Elf Druid", frozenset({"Goblin", "Druid"}))
    assert not matches_subtypes("Creature — Elf Druid", frozenset({"Goblin"}))
    assert not matches_subtypes("Instant", frozenset({"Elf"}))
    assert matches_subtypes("Instant", frozenset())


def test_types_and_subtypes_narrow_each_other() -> None:
    elf_creature = _row(
        name="Llanowar Elves", oracle_id="llanowar", type_line="Creature — Elf Druid"
    )
    elf_land = _row(
        name="Elf Land", oracle_id="elfland", type_line="Land — Elf"
    )
    goblin = _row(
        name="Goblin Guide", oracle_id="guide", type_line="Creature — Goblin Scout"
    )
    state = InventoryFilterState(
        types=frozenset({"Creature"}), subtypes=frozenset({"Elf"})
    )
    assert matches_panel_filters(elf_creature, state)
    assert not matches_panel_filters(elf_land, state)
    assert not matches_panel_filters(goblin, state)


def test_only_with_free_hides_fully_assigned_cards() -> None:
    free = _row(free_copies=1)
    spent = _row(name="Sol Ring", oracle_id="sol", free_copies=0)
    state = InventoryFilterState(only_with_free=True)
    assert matches_panel_filters(free, state)
    assert not matches_panel_filters(spent, state)
    assert state.is_active
    assert not InventoryFilterState().is_active


def test_subtypes_alone_activate_the_filter() -> None:
    assert InventoryFilterState(subtypes=frozenset({"Elf"})).is_active


def test_cmc_multiple_conditions_and() -> None:
    bolt = _row(cmc=1)
    state = InventoryFilterState(
        cmc_conditions=(
            CmcCondition(">=", 1),
            CmcCondition("<=", 2),
        )
    )
    assert matches_panel_filters(bolt, state)
    assert not matches_panel_filters(
        _row(name="Big", oracle_id="big", cmc=5), state
    )


def test_cmc_satisfiable_detects_empty_and_impossible_sets() -> None:
    assert cmc_conditions_satisfiable(())
    assert cmc_conditions_satisfiable((CmcCondition("=", 1),))
    assert cmc_conditions_satisfiable(
        (CmcCondition(">=", 1), CmcCondition("<=", 3))
    )
    assert not cmc_conditions_satisfiable(
        (CmcCondition("=", 1), CmcCondition("=", 3))
    )
    assert not cmc_conditions_satisfiable(
        (CmcCondition(">", 5), CmcCondition("<", 3))
    )
    assert not cmc_conditions_satisfiable(
        (CmcCondition("=", 2), CmcCondition("!=", 2))
    )


def test_resolve_cmc_add_blocks_duplicates_and_conflicts() -> None:
    existing = (CmcCondition("=", 1),)
    assert resolve_cmc_add(existing, "=", 1).status is CmcAddStatus.DUPLICATE
    assert resolve_cmc_add(existing, "=", 3).status is CmcAddStatus.CONFLICT
    assert resolve_cmc_add(existing, ">=", 0).status is CmcAddStatus.OK
    assert resolve_cmc_add((), "=", 1).can_add


def test_cmc_conditions_issue_prefers_duplicate_over_ok() -> None:
    assert cmc_conditions_issue(()) is CmcSetIssue.NONE
    assert (
        cmc_conditions_issue((CmcCondition(">=", 2), CmcCondition(">=", 2)))
        is CmcSetIssue.DUPLICATE
    )
    assert (
        cmc_conditions_issue((CmcCondition("=", 1), CmcCondition("=", 3)))
        is CmcSetIssue.IMPOSSIBLE
    )


def test_exclude_any_armed_hides_assigned_keeps_free() -> None:
    free = _row()
    assigned = _row(name="Sol Ring", oracle_id="sol", assigned_deck_ids=frozenset({7}))
    state = InventoryFilterState(exclude_any_armed=True)
    assert matches_panel_filters(free, state)
    assert not matches_panel_filters(assigned, state)
    assert InventoryFilterState(exclude_any_armed=True).is_active


def test_exclude_deck_ids_only_intersecting() -> None:
    in_a = _row(name="A", oracle_id="a", assigned_deck_ids=frozenset({1}))
    in_b = _row(name="B", oracle_id="b", assigned_deck_ids=frozenset({2}))
    free = _row()
    state = InventoryFilterState(exclude_deck_ids=frozenset({1}))
    assert not matches_panel_filters(in_a, state)
    assert matches_panel_filters(in_b, state)
    assert matches_panel_filters(free, state)


def test_exclude_deck_or_any_armed_with_type() -> None:
    creature_free = _row(
        name="Elf",
        oracle_id="elf",
        type_line="Creature — Elf",
        color_identity="G",
    )
    creature_armed = _row(
        name="Bear",
        oracle_id="bear",
        type_line="Creature — Bear",
        color_identity="G",
        assigned_deck_ids=frozenset({3}),
    )
    instant_armed = _row(
        name="Bolt",
        oracle_id="bolt2",
        type_line="Instant",
        assigned_deck_ids=frozenset({9}),
    )
    state = InventoryFilterState(
        types=frozenset({"Creature"}),
        exclude_any_armed=True,
    )
    assert matches_panel_filters(creature_free, state)
    assert not matches_panel_filters(creature_armed, state)
    assert not matches_panel_filters(instant_armed, state)

    specific = InventoryFilterState(
        types=frozenset({"Creature"}),
        exclude_deck_ids=frozenset({3}),
    )
    assert matches_panel_filters(creature_free, specific)
    assert not matches_panel_filters(creature_armed, specific)


def test_filter_combines_name_panel_and_scryfall_ids() -> None:
    bolt = _row()
    bird = _row(
        name="Birds of Paradise",
        oracle_id="bop",
        type_line="Creature — Bird",
        color_identity="G",
        cmc=1,
    )
    wrath = _row(
        name="Wrath of God",
        oracle_id="wrath",
        type_line="Sorcery",
        color_identity="W",
        cmc=4,
    )
    panel = InventoryFilterState(types=frozenset({"Instant", "Sorcery"}))
    hits = filter_inventory_cards(
        [bolt, bird, wrath],
        name_query="o",
        panel=panel,
        scryfall_oracle_ids={"bolt", "bop", "wrath"},
    )
    assert [row.oracle_id for row in hits] == ["bolt", "wrath"]


def test_rarity_filter_inactive_when_empty_or_all_four() -> None:
    assert not InventoryFilterState(rarities=frozenset()).rarity_filter_active
    assert not InventoryFilterState(
        rarities=frozenset("CURM")
    ).rarity_filter_active
    assert InventoryFilterState(rarities=frozenset({"R", "M"})).rarity_filter_active


def test_rarity_match_is_or_across_selected() -> None:
    assert matches_rarity(frozenset({"rare"}), frozenset({"R"}))
    assert matches_rarity(frozenset({"mythic", "common"}), frozenset({"M", "U"}))
    assert not matches_rarity(frozenset({"common"}), frozenset({"R", "M"}))
    assert not matches_rarity(frozenset(), frozenset({"C"}))
    assert not matches_rarity(frozenset({"special"}), frozenset({"R"}))


def test_no_chips_when_nothing_is_active() -> None:
    assert filter_chips(InventoryFilterState()) == ()
    assert active_filter_count(InventoryFilterState()) == 0


def test_chips_follow_dialog_order_and_split_by_item() -> None:
    state = InventoryFilterState(
        only_with_free=True,
        types=frozenset({"Land", "Creature"}),
        subtypes=frozenset({"Elf"}),
        exclude_any_armed=True,
        exclude_deck_ids=frozenset({4, 2}),
        colors=frozenset({"R"}),
        rarities=frozenset({"M"}),
        cmc_conditions=(CmcCondition("=", 1), CmcCondition(">", 3)),
    )
    assert filter_chips(state) == (
        FilterChip(FilterChipKind.ONLY_FREE),
        FilterChip(FilterChipKind.TYPE, "Creature"),
        FilterChip(FilterChipKind.TYPE, "Land"),
        FilterChip(FilterChipKind.SUBTYPE, "Elf"),
        FilterChip(FilterChipKind.ANY_ARMED),
        FilterChip(FilterChipKind.DECK, "2"),
        FilterChip(FilterChipKind.DECK, "4"),
        FilterChip(FilterChipKind.COLORS),
        FilterChip(FilterChipKind.RARITY),
        FilterChip(FilterChipKind.CMC, "0"),
        FilterChip(FilterChipKind.CMC, "1"),
    )
    assert active_filter_count(state) == 11


def test_colorless_and_letters_never_produce_two_color_chips() -> None:
    colorless = InventoryFilterState(
        colors=frozenset({"R"}), only_colorless=True
    )
    assert filter_chips(colorless) == (FilterChip(FilterChipKind.COLORLESS),)


def test_chip_count_agrees_with_is_active() -> None:
    """The button counter and the ✓ it replaced must never disagree."""
    states = [
        InventoryFilterState(),
        InventoryFilterState(colors=frozenset("WUBRG")),
        InventoryFilterState(rarities=frozenset("CURM")),
        InventoryFilterState(only_colorless=True),
        InventoryFilterState(types=frozenset({"Land"})),
        InventoryFilterState(
            colors=frozenset("WUBRG"), color_mode=ColorMode.EXACT
        ),
    ]
    for state in states:
        assert bool(active_filter_count(state)) is state.is_active


def test_rarity_panel_filter() -> None:
    common = _row(rarity="common")
    mythic = _row(name="Omniscience", oracle_id="omni", rarity="mythic", cmc=10)
    mixed = _row(
        name="Shock",
        oracle_id="shock",
        rarity="common",
        rarities=frozenset({"common", "rare"}),
    )
    state = InventoryFilterState(rarities=frozenset({"R", "M"}))
    assert not matches_panel_filters(common, state)
    assert matches_panel_filters(mythic, state)
    assert matches_panel_filters(mixed, state)
