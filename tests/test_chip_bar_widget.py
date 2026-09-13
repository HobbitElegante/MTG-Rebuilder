"""Widget tests for the removable-chip bar.

Skipped wherever PySide6 cannot be imported; see the note in
``test_inventory_image_grid_widget.py`` for why this is not ``importorskip``.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication

    from mtg_rebuilder.ui.widgets.chip_bar import Chip, ChipBar
except ImportError as exc:  # pragma: no cover - headless CI without Qt libs
    pytest.skip(f"PySide6 unavailable: {exc}", allow_module_level=True)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def bar(app):
    widget = ChipBar()
    yield widget
    widget.deleteLater()


def test_an_empty_bar_hides_itself(bar):
    bar.set_chips([Chip("a", "Type: Land")])
    bar.set_chips([])

    assert bar.isHidden()
    assert bar.chips() == ()
    assert bar._layout.count() == 0


def test_chips_are_rebuilt_without_leaking_widgets(bar):
    bar.set_chips([Chip("a", "Type: Land"), Chip("b", "Subtype: Elf")])
    assert bar._layout.count() == 2

    bar.set_chips([Chip("a", "Type: Land")])

    assert bar._layout.count() == 1
    assert [chip.label for chip in bar.chips()] == ["Type: Land"]


def test_removing_a_chip_emits_its_key(bar):
    removed = []
    bar.chip_removed.connect(removed.append)
    bar.set_chips([Chip(7, "Not in: Kellan"), Chip(9, "Not in: Athreos")])

    # The ✕ is the second widget of the chip frame.
    frame = bar._layout.itemAt(1).widget()
    frame.layout().itemAt(1).widget().click()

    assert removed == [9]


def test_clear_all_only_appears_once_it_has_a_label(bar):
    bar.set_chips([Chip("a", "Type: Land")])
    assert bar._layout.count() == 1

    bar.set_texts(remove_tooltip="Remove this filter", clear_text="Clear all")

    # One chip plus the trailing clear button.
    assert bar._layout.count() == 2
    cleared = []
    bar.cleared.connect(lambda: cleared.append(1))
    bar._clear_button.click()
    assert cleared == [1]


def test_the_clear_button_survives_rebuilds(bar):
    """It is reused rather than deleted, so a rebuild must not drop it."""
    bar.set_texts(remove_tooltip="Remove", clear_text="Clear all")
    bar.set_chips([Chip("a", "Type: Land")])
    bar.set_chips([Chip("b", "Type: Creature"), Chip("c", "Subtype: Elf")])

    assert bar._layout.count() == 3
    assert bar._layout.itemAt(2).widget() is bar._clear_button


def test_chips_wrap_to_a_second_line_when_narrow(bar):
    bar.set_chips([Chip(index, f"Filter number {index}") for index in range(8)])
    wide = bar._layout.heightForWidth(2000)
    narrow = bar._layout.heightForWidth(150)
    assert narrow > wide


def test_the_remove_tooltip_is_applied_to_every_chip(bar):
    bar.set_texts(remove_tooltip="Remove this filter")
    bar.set_chips([Chip("a", "Type: Land"), Chip("b", "Subtype: Elf")])

    for index in range(2):
        frame = bar._layout.itemAt(index).widget()
        remove = frame.layout().itemAt(1).widget()
        assert remove.toolTip() == "Remove this filter"
