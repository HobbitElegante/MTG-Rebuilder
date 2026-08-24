"""Widget-level tests for the Inventory filter dialog.

Skipped wherever PySide6 cannot be imported; see the note in
``test_inventory_image_grid_widget.py`` for why this is not ``importorskip``.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication

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
    assert dialog._subtype_queue.count() == 1
    assert dialog._subtype_queue.item(0).text() == "Elf"


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
    assert dialog._subtype_queue.count() == 0


def test_section_help_lives_in_tooltips(dialog):
    headers = [header for header, _title, _hint in dialog._headers]
    assert headers
    for header in headers:
        assert header.toolTip()
        # The paragraph is gone; only the title plus the ⓘ marker is painted.
        assert len(header.text()) < len(header.toolTip())


def test_empty_form_opens_at_its_natural_height(dialog):
    """QScrollArea caps its own hint at 24 lines; the dialog must ignore that."""
    dialog.show()
    content = dialog._scroll.widget().sizeHint().height()

    assert content > dialog._scroll.sizeHint().height()
    assert dialog.sizeHint().height() >= content
    assert content <= dialog._screen_height_cap()
    dialog.hide()


def test_a_long_form_is_capped_to_the_screen(dialog):
    dialog.show()
    cap = dialog._screen_height_cap()

    for _ in range(12):
        dialog._add_cmc_condition()
    # Layout requests are posted, so the size hints are stale until delivered.
    QApplication.processEvents()

    assert dialog._scroll.widget().sizeHint().height() > cap
    assert dialog.sizeHint().height() <= cap
    dialog.hide()


def test_selected_lists_grow_with_their_items(dialog):
    dialog.set_subtypes(("Elf", "Goblin", "Zombie"))
    dialog._subtype_combo.setCurrentText("Elf")
    dialog._add_selected_subtype()
    one_item = dialog._subtype_queue.height()

    dialog._subtype_combo.setCurrentText("Goblin")
    dialog._add_selected_subtype()

    assert dialog._subtype_queue.height() > one_item
