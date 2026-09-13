"""Parse Scryfall brace symbols for UI rendering (no Qt).

Tier B ships SVGs for W/U/B/R/G/C, generic numbers 0–15, and X. Hybrids,
Phyrexian costs and oddballs fall outside this set — callers skip them or
keep the brace text as a fallback.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

# Filenames under resources/card-symbols/{code}.svg (no braces).
TIER_B_CODES: frozenset[str] = frozenset(
    {*"WUBRGCX", *(str(n) for n in range(0, 16))}
)

_WUBRG_ORDER = ("W", "U", "B", "R", "G")

_SYMBOL_RE = re.compile(r"\{([^}]+)\}")


def normalize_symbol_code(inner: str) -> str:
    """Map a brace interior (``G``, ``w``, ``10``) to a resource code."""
    text = inner.strip()
    if not text:
        return text
    if text.isdigit() or (text[0].isdigit() and text.replace(".", "", 1).isdigit()):
        # Half-mana and similar stay as-is; only exact ints 0–15 are tier B.
        try:
            as_int = int(float(text))
            if float(text) == as_int:
                return str(as_int)
        except ValueError:
            pass
        return text
    return text.upper()


def is_tier_b_code(code: str) -> bool:
    return code in TIER_B_CODES


def parse_brace_symbols(text: str | None) -> tuple[str, ...]:
    """Inner parts of every ``{…}`` in order (front face only if ``//``)."""
    if not text:
        return ()
    front = text.split("//", 1)[0]
    return tuple(_SYMBOL_RE.findall(front))


def color_identity_codes(color_identity: str | None) -> tuple[str, ...]:
    """WUBRG letters present, in W→G order (Scryfall identity order)."""
    if not color_identity:
        return ()
    have = {letter for letter in color_identity.upper() if letter in _WUBRG_ORDER}
    return tuple(letter for letter in _WUBRG_ORDER if letter in have)


def renderable_codes(inners: Iterable[str]) -> tuple[str, ...]:
    """Normalize and keep only codes we ship as SVGs."""
    out: list[str] = []
    for inner in inners:
        code = normalize_symbol_code(inner)
        if is_tier_b_code(code):
            out.append(code)
    return tuple(out)


def mana_cost_codes(mana_cost: str | None) -> tuple[str, ...]:
    """Tier-B codes from a Scryfall ``mana_cost`` string, in print order."""
    return renderable_codes(parse_brace_symbols(mana_cost))
