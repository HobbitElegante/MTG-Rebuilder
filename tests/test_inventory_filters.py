"""Tests for inventory panel filters (type / subtype / colors / rarity / CMC / decks)."""

from mtg_rebuilder.algorithms.inventory_filters import (
    CmcCondition,
    InventoryFilterState,
    filter_inventory_cards,
    matches_color_identity_at_most,
    matches_panel_filters,
    matches_rarity,
    matches_subtypes,
    matches_type_line,
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
