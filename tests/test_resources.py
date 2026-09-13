"""The app icon and Scryfall card symbols must travel with the package."""

from mtg_rebuilder.algorithms.mana_symbols import TIER_B_CODES
from mtg_rebuilder.resources import APP_ICON, CARD_SYMBOLS_DIR

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def test_app_icon_is_bundled_with_the_package():
    assert APP_ICON.is_file()
    assert APP_ICON.parent.name == "resources"


def test_app_icon_is_a_readable_png():
    assert APP_ICON.read_bytes()[:8] == PNG_MAGIC


def test_tier_b_card_symbols_are_bundled():
    assert CARD_SYMBOLS_DIR.is_dir()
    assert (CARD_SYMBOLS_DIR / "ATTRIBUTION.txt").is_file()
    for code in sorted(TIER_B_CODES):
        path = CARD_SYMBOLS_DIR / f"{code}.svg"
        assert path.is_file(), path.name
        assert path.read_text(encoding="utf-8").lstrip().startswith("<svg")
