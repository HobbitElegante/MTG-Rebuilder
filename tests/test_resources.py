"""The app icon and Scryfall card symbols must travel with the package."""

from mtg_rebuilder.algorithms.mana_symbols import SYMBOL_CODES, symbol_asset_name
from mtg_rebuilder.resources import APP_ICON, CARD_SYMBOLS_DIR

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def test_app_icon_is_bundled_with_the_package():
    assert APP_ICON.is_file()
    assert APP_ICON.parent.name == "resources"


def test_app_icon_is_a_readable_png():
    assert APP_ICON.read_bytes()[:8] == PNG_MAGIC


def test_every_card_symbol_code_is_bundled():
    assert CARD_SYMBOLS_DIR.is_dir()
    assert (CARD_SYMBOLS_DIR / "ATTRIBUTION.txt").is_file()
    for code in sorted(SYMBOL_CODES):
        path = CARD_SYMBOLS_DIR / f"{symbol_asset_name(code)}.svg"
        assert path.is_file(), path.name
        assert path.read_text(encoding="utf-8").lstrip().startswith("<svg")
