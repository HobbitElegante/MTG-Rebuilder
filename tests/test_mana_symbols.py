"""Brace-symbol parsing for the bundled Scryfall SVGs."""

from mtg_rebuilder.algorithms.mana_symbols import (
    COMPOUND_CODES,
    SYMBOL_CODES,
    color_identity_codes,
    is_symbol_code,
    mana_cost_codes,
    mana_cost_text,
    normalize_symbol_code,
    parse_brace_symbols,
    renderable_codes,
    symbol_asset_name,
)


def test_symbol_codes_cover_identity_costs_hybrids_and_phyrexian() -> None:
    assert "G" in SYMBOL_CODES
    assert "C" in SYMBOL_CODES
    assert "20" in SYMBOL_CODES
    assert "X" in SYMBOL_CODES
    assert "S" in SYMBOL_CODES
    assert "W/U" in SYMBOL_CODES
    assert "2/G" in SYMBOL_CODES
    assert "C/R" in SYMBOL_CODES
    assert "B/P" in SYMBOL_CODES
    assert "R/G/P" in SYMBOL_CODES
    # Loyalty, tap and Un-set oddballs stay out.
    assert "21" not in SYMBOL_CODES
    assert "T" not in SYMBOL_CODES
    assert "½" not in SYMBOL_CODES


def test_compound_codes_are_the_full_hybrid_and_phyrexian_set() -> None:
    # 10 hybrid pairs + 5 twobrid + 5 colorless hybrid + 5 Phyrexian
    # + 10 Phyrexian hybrids.
    assert len(COMPOUND_CODES) == 35
    assert all("/" in code for code in COMPOUND_CODES)


def test_parse_brace_symbols_front_face_only() -> None:
    assert parse_brace_symbols("{2}{G}{G}") == ("2", "G", "G")
    assert parse_brace_symbols("{U} // {B}") == ("U",)
    assert parse_brace_symbols(None) == ()
    assert parse_brace_symbols("") == ()


def test_color_identity_codes_wubrg_order() -> None:
    assert color_identity_codes("RG") == ("R", "G")
    assert color_identity_codes("GWR") == ("W", "R", "G")
    assert color_identity_codes(None) == ()
    assert color_identity_codes("") == ()


def test_mana_cost_codes_keep_hybrids_in_print_order() -> None:
    assert mana_cost_codes("{2}{W/U}{G}") == ("2", "W/U", "G")
    assert mana_cost_codes("{X}{X}{R}") == ("X", "X", "R")
    assert mana_cost_codes("{C}") == ("C",)
    assert mana_cost_codes("{B/G/P}{2/R}{S}") == ("B/G/P", "2/R", "S")
    assert renderable_codes(["g", "u/w", "3"]) == ("G", "W/U", "3")


def test_normalize_symbol_code_canonicalizes_compounds() -> None:
    assert normalize_symbol_code("g") == "G"
    assert normalize_symbol_code("10") == "10"
    # Scryfall's own order wins, whichever way the parts arrive.
    assert normalize_symbol_code("u/w") == "W/U"
    assert normalize_symbol_code("p/g") == "G/P"
    assert normalize_symbol_code("P/U/W") == "W/U/P"
    assert normalize_symbol_code("w/w") == "W/W"
    assert is_symbol_code("W/U")
    assert not is_symbol_code("W/W")


def test_symbol_asset_name_drops_slashes() -> None:
    assert symbol_asset_name("W/U") == "WU"
    assert symbol_asset_name("B/G/P") == "BGP"
    assert symbol_asset_name("10") == "10"


def test_mana_cost_text_is_brace_free() -> None:
    assert mana_cost_text("{2}{W/U}{R}") == "2 W/U R"
    assert mana_cost_text("{U} // {B}") == "U"
    assert mana_cost_text("") == ""
    assert mana_cost_text(None) == ""
