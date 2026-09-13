"""Brace-symbol parsing for bundled Scryfall SVGs (tier B)."""

from mtg_rebuilder.algorithms.mana_symbols import (
    TIER_B_CODES,
    color_identity_codes,
    is_tier_b_code,
    mana_cost_codes,
    normalize_symbol_code,
    parse_brace_symbols,
    renderable_codes,
)


def test_tier_b_covers_identity_and_simple_costs() -> None:
    assert "G" in TIER_B_CODES
    assert "C" in TIER_B_CODES
    assert "15" in TIER_B_CODES
    assert "X" in TIER_B_CODES
    assert "16" not in TIER_B_CODES
    assert "W/U" not in TIER_B_CODES


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


def test_mana_cost_codes_skips_hybrids_keeps_tier_b() -> None:
    assert mana_cost_codes("{2}{W/U}{G}") == ("2", "G")
    assert mana_cost_codes("{X}{X}{R}") == ("X", "X", "R")
    assert mana_cost_codes("{C}") == ("C",)
    assert normalize_symbol_code("g") == "G"
    assert is_tier_b_code("10")
    assert renderable_codes(["g", "W/U", "3"]) == ("G", "3")
