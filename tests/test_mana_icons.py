"""Qt rendering of bundled Scryfall mana SVGs."""

from __future__ import annotations

import pytest

try:
    from PySide6.QtWidgets import QApplication
except ImportError as exc:  # pragma: no cover - headless CI without libEGL
    pytest.skip(f"PySide6 unavailable: {exc}", allow_module_level=True)

from mtg_rebuilder.ui.mana_icons import (
    color_identity_pixmap,
    compose_symbol_pixmap,
    load_symbol_pixmap,
    mana_cost_pixmap,
    pips_rich_html,
    symbol_svg_path,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_load_and_compose_symbols(qapp):
    green = load_symbol_pixmap("G", 16)
    assert green is not None
    assert not green.isNull()
    assert green.width() == 16

    strip = compose_symbol_pixmap(("2", "G", "G"), size=12)
    assert strip is not None
    assert strip.width() == 12 * 3 + 2

    identity = color_identity_pixmap("RG", size=14)
    assert identity is not None
    assert identity.width() == 14 * 2 + 1

    cost = mana_cost_pixmap("{2}{W/U}{R}", size=14)
    assert cost is not None
    # Hybrid skipped; 2 + R remain.
    assert cost.width() == 14 * 2 + 1

    assert symbol_svg_path("W/U") is None
    html = pips_rich_html((("G", 3), ("C", 1)))
    assert "G.svg" in html
    assert "3" in html
