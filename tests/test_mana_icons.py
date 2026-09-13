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
    mana_cost_rich_html,
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
    assert cost.width() == 14 * 3 + 2

    assert symbol_svg_path("W/U") == symbol_svg_path("U/W")
    assert symbol_svg_path("B/G/P") is not None
    html = pips_rich_html((("G", 3), ("C", 1)))
    assert "G.svg" in html
    assert "3" in html


def test_mana_cost_pixmap_is_all_or_nothing(qapp):
    # {½} is outside the bundle, so a strip would understate the cost.
    assert mana_cost_pixmap("{½}{W}", size=14) is None
    assert mana_cost_pixmap("", size=14) is None
    assert mana_cost_pixmap(None, size=14) is None


def test_cost_and_identity_strips_are_cached(qapp):
    # Inventory composes one strip per row (~1.9k); the cache is what keeps the
    # rebuild off the per-row painting path.
    assert mana_cost_pixmap("{3}{G}", size=14) is mana_cost_pixmap("{3}{G}", size=14)
    assert color_identity_pixmap("WU", size=14) is color_identity_pixmap("WU", size=14)


def test_mana_cost_rich_html_keeps_unknown_symbols_as_text(qapp):
    html = mana_cost_rich_html("{2}{W/U}{S}", size=14)
    assert "WU.svg" in html
    assert "S.svg" in html
    assert mana_cost_rich_html("{½}{W}", size=14).startswith("½")
    assert mana_cost_rich_html(None) == ""
