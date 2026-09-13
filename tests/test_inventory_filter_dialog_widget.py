"""Widget-level tests for the Inventory filter dialog.

Skipped wherever PySide6 cannot be imported; see the note in
``test_inventory_image_grid_widget.py`` for why this is not ``importorskip``.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication

    from mtg_rebuilder.algorithms.inventory_filters import (
        ColorMode,
        FilterChip,
        FilterChipKind,
    )
    from mtg_rebuilder.i18n import Translator
    from mtg_rebuilder.ui.widgets.inventory_filter_panel import InventoryFilterDialog
except ImportError as exc:  # pragma: no cover - headless CI without Qt libs
    pytest.skip(f"PySide6 unavailable: {exc}", allow_module_level=True)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def dialog(app):
    widget = InventoryFilterDialog(Translator("en"))
    yield widget
    widget.deleteLater()


def test_type_checkboxes_feed_the_state(dialog):
    changes = []
    dialog.filters_changed.connect(lambda: changes.append(1))

    dialog._type_checks["Creature"].setChecked(True)
    dialog._type_checks["Land"].setChecked(True)

    assert dialog.filter_state().types == frozenset({"Creature", "Land"})
    assert len(changes) == 2


def test_subtype_is_added_by_typing_and_shows_in_the_queue(dialog):
    dialog.set_subtypes(("Aura", "Elf", "Equipment"))
    assert not dialog._subtype_queue_group.isVisible()

    dialog._subtype_combo.setCurrentText("Elf")
    dialog._add_selected_subtype()

    assert dialog.filter_state().subtypes == frozenset({"Elf"})
    assert [chip.label for chip in dialog._subtype_chips.chips()] == ["Elf"]


def test_subtype_picker_survives_a_catalog_refresh(dialog):
    dialog.set_subtypes(("Elf", "Goblin"))
    dialog._subtype_combo.setCurrentText("Goblin")
    dialog._add_selected_subtype()

    dialog.set_subtypes(("Elf", "Goblin", "Zombie"))

    assert dialog.filter_state().subtypes == frozenset({"Goblin"})
    assert dialog._subtype_combo.count() == 3


def test_only_free_checkbox_feeds_the_state(dialog):
    assert not dialog.filter_state().only_with_free
    dialog._only_free.setChecked(True)
    assert dialog.filter_state().only_with_free


def test_clear_resets_types_subtypes_and_availability(dialog):
    dialog.set_subtypes(("Elf",))
    dialog._type_checks["Creature"].setChecked(True)
    dialog._only_free.setChecked(True)
    dialog._subtype_combo.setCurrentText("Elf")
    dialog._add_selected_subtype()
    assert dialog.filter_state().is_active

    dialog.clear_filters()

    assert not dialog.filter_state().is_active
    assert dialog._subtype_chips.chips() == ()


def test_section_help_lives_in_tooltips(dialog):
    headers = [header for header, _title, _hint in dialog._headers]
    assert headers
    for header in headers:
        assert header.toolTip()
        # The paragraph is gone; only the title plus the ⓘ marker is painted.
        assert len(header.text()) < len(header.toolTip())


def test_empty_form_opens_at_its_natural_height(dialog):
    """Open tall enough that the form does not scroll when it fits the screen.

    Qt's first-show adjustSize caps top-levels at 2/3 of the screen; the dialog
    must resize to its own sizeHint (85% cap) instead.
    """
    dialog.show()
    QApplication.processEvents()
    content = dialog._scroll.widget().sizeHint().height()
    two_thirds = int(dialog.screen().availableGeometry().height() * 2 / 3)

    assert content > dialog._scroll.sizeHint().height()
    assert dialog.sizeHint().height() >= content
    assert content <= dialog._screen_height_cap()
    # The form itself is taller than Qt's adjustSize cap on this screen.
    assert dialog.sizeHint().height() > two_thirds
    assert dialog.height() == dialog.sizeHint().height()
    assert dialog._scroll.verticalScrollBar().maximum() == 0
    dialog.hide()


def test_a_long_form_is_capped_to_the_screen(dialog):
    dialog.show()
    cap = dialog._screen_height_cap()

    # Compatible AND conditions (any MV outside 0–11 still matches).
    dialog._cmc_op.setCurrentText("!=")
    for value in range(12):
        dialog._cmc_value.setValue(value)
        dialog._add_cmc_condition()
    # Layout requests are posted, so the size hints are stale until delivered.
    QApplication.processEvents()

    assert dialog._scroll.widget().sizeHint().height() > cap
    assert dialog.sizeHint().height() <= cap
    dialog.hide()


def test_cmc_add_blocks_duplicates_and_impossible_conditions(dialog):
    dialog._cmc_op.setCurrentText("=")
    dialog._cmc_value.setValue(1)
    assert dialog._cmc_add_button.isEnabled()
    dialog._add_cmc_condition()

    assert not dialog._cmc_add_button.isEnabled()
    assert "1" in dialog._cmc_hint.text()

    dialog._cmc_value.setValue(3)
    # = 1 already committed; = 3 would empty the result set.
    assert not dialog._cmc_add_button.isEnabled()
    assert dialog._cmc_hint.text()

    dialog._cmc_op.setCurrentText(">=")
    dialog._cmc_value.setValue(0)
    assert dialog._cmc_add_button.isEnabled()
    dialog._add_cmc_condition()
    assert len(dialog.filter_state().cmc_conditions) == 2


def test_editing_cmc_rows_warns_when_the_set_becomes_impossible(dialog):
    dialog._cmc_op.setCurrentText(">=")
    dialog._cmc_value.setValue(5)
    dialog._add_cmc_condition()
    dialog._cmc_op.setCurrentText("<=")
    dialog._cmc_value.setValue(10)
    dialog._add_cmc_condition()

    _op, spin, _remove = dialog._cmc_rows[1]
    spin.setValue(3)

    assert not dialog._cmc_hint.isHidden()
    assert dialog._cmc_hint.text()
    # Already-impossible set: every further append stays blocked.
    assert not dialog._cmc_add_button.isEnabled()


def test_each_selection_gets_its_own_removable_chip(dialog):
    dialog.set_subtypes(("Elf", "Goblin", "Zombie"))
    for subtype in ("Elf", "Goblin"):
        dialog._subtype_combo.setCurrentText(subtype)
        dialog._add_selected_subtype()

    assert [chip.label for chip in dialog._subtype_chips.chips()] == [
        "Elf",
        "Goblin",
    ]

    dialog._on_subtype_chip_removed("Elf")

    assert dialog.filter_state().subtypes == frozenset({"Goblin"})
    assert [chip.label for chip in dialog._subtype_chips.chips()] == ["Goblin"]


def test_color_mode_combo_feeds_the_state(dialog):
    assert dialog.filter_state().color_mode is ColorMode.AT_MOST

    for index, mode in enumerate(ColorMode):
        dialog._color_mode_combo.setCurrentIndex(index)
        assert dialog.filter_state().color_mode is mode


def test_only_colorless_greys_out_the_letters_it_overrides(dialog):
    assert dialog._color_mode_combo.isEnabled()

    dialog._only_colorless.setChecked(True)

    state = dialog.filter_state()
    assert state.only_colorless
    assert state.is_active
    assert not dialog._color_mode_combo.isEnabled()
    assert all(not box.isEnabled() for box in dialog._color_checks.values())

    dialog._only_colorless.setChecked(False)
    assert dialog._color_mode_combo.isEnabled()
    assert all(box.isEnabled() for box in dialog._color_checks.values())


def test_colorless_is_reachable_where_checkboxes_alone_are_not(dialog):
    """Zero letters means "no filter", so this is the only way to say colorless."""
    assert not dialog.filter_state().is_active
    dialog._only_colorless.setChecked(True)
    assert dialog.filter_state().is_active


def test_add_is_disabled_until_the_text_resolves(dialog):
    dialog.set_subtypes(("Elemental", "Elf", "Equipment"))
    assert not dialog._subtype_add_button.isEnabled()

    dialog._subtype_combo.setCurrentText("El")
    assert not dialog._subtype_add_button.isEnabled()
    # The dialog is never shown here, so isVisible() stays False for children;
    # isHidden() is what tracks the explicit setVisible call.
    assert not dialog._subtype_hint.isHidden()
    ambiguous = dialog._subtype_hint.text()
    assert "El" in ambiguous

    dialog._subtype_combo.setCurrentText("Sliver")
    assert not dialog._subtype_add_button.isEnabled()
    assert dialog._subtype_hint.text() != ambiguous

    dialog._subtype_combo.setCurrentText("Elf")
    assert dialog._subtype_add_button.isEnabled()
    assert not dialog._subtype_hint.text()


def test_adding_twice_says_so_instead_of_doing_nothing(dialog):
    dialog.set_subtypes(("Elf", "Goblin"))
    dialog._subtype_combo.setCurrentText("Elf")
    dialog._add_selected_subtype()

    dialog._subtype_combo.setCurrentText("Elf")

    assert not dialog._subtype_add_button.isEnabled()
    assert "Elf" in dialog._subtype_hint.text()
    assert dialog.filter_state().subtypes == frozenset({"Elf"})


def test_unresolvable_add_leaves_the_state_alone(dialog):
    dialog.set_subtypes(("Elemental", "Elf"))
    changes = []
    dialog.filters_changed.connect(lambda: changes.append(1))

    dialog._subtype_combo.setCurrentText("El")
    dialog._add_selected_subtype()

    assert not changes
    assert dialog.filter_state().subtypes == frozenset()


def test_armed_deck_picker_reports_an_unknown_deck(dialog):
    dialog.set_armed_decks([(1, "Kellan"), (2, "Athreos")])

    dialog._deck_combo.setCurrentText("Kellan")
    assert dialog._deck_add_button.isEnabled()
    dialog._add_selected_deck()
    assert dialog.filter_state().exclude_deck_ids == frozenset({1})
    assert dialog.selected_deck_names() == {1: "Kellan"}

    dialog._deck_combo.setCurrentText("Muldrotha")
    assert not dialog._deck_add_button.isEnabled()
    assert dialog._deck_hint.text()


def test_remove_chip_clears_each_kind_of_filter(dialog):
    dialog.set_subtypes(("Elf",))
    dialog.set_armed_decks([(3, "Kellan")])
    dialog._only_free.setChecked(True)
    dialog._exclude_any_armed.setChecked(True)
    dialog._type_checks["Creature"].setChecked(True)
    dialog._color_checks["R"].setChecked(True)
    dialog._rarity_checks["M"].setChecked(True)
    dialog._subtype_combo.setCurrentText("Elf")
    dialog._add_selected_subtype()
    dialog._deck_combo.setCurrentText("Kellan")
    dialog._add_selected_deck()
    dialog._add_cmc_condition()

    for chip in (
        FilterChip(FilterChipKind.ONLY_FREE),
        FilterChip(FilterChipKind.TYPE, "Creature"),
        FilterChip(FilterChipKind.SUBTYPE, "Elf"),
        FilterChip(FilterChipKind.ANY_ARMED),
        FilterChip(FilterChipKind.DECK, "3"),
        FilterChip(FilterChipKind.COLORS),
        FilterChip(FilterChipKind.RARITY),
        FilterChip(FilterChipKind.CMC, "0"),
    ):
        dialog.remove_chip(chip)

    assert not dialog.filter_state().is_active


def test_removing_the_color_chip_clears_every_letter_at_once(dialog):
    dialog._color_checks["R"].setChecked(True)
    dialog._color_checks["G"].setChecked(True)
    changes = []
    dialog.filters_changed.connect(lambda: changes.append(1))

    dialog.remove_chip(FilterChip(FilterChipKind.COLORS))

    assert dialog.filter_state().colors == frozenset()
    assert len(changes) == 1


def test_removing_an_unset_chip_is_a_no_op(dialog):
    changes = []
    dialog.filters_changed.connect(lambda: changes.append(1))

    dialog.remove_chip(FilterChip(FilterChipKind.RARITY))
    dialog.remove_chip(FilterChip(FilterChipKind.CMC, "4"))
    dialog.remove_chip(FilterChip(FilterChipKind.SUBTYPE, "Sliver"))

    assert not changes
    assert not dialog.filter_state().is_active
