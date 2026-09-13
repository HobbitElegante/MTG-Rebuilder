"""Parse Scryfall brace symbols for UI rendering (no Qt).

The bundled set covers every symbol a printed ``mana_cost`` can use: W/U/B/R/G/C,
generic 0–20, X, snow, hybrids (``{W/U}``, ``{2/W}``, ``{C/W}``) and Phyrexian
(``{W/P}``, ``{W/U/P}``). Loyalty, tap and Un-set oddballs fall outside it —
callers skip them or keep the brace text as a fallback.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

_WUBRG_ORDER = ("W", "U", "B", "R", "G")

# Scryfall's canonical ordering, mirrored so the asset names match theirs.
_HYBRID_PAIRS = (
    "W/U",
    "W/B",
    "U/B",
    "U/R",
    "B/R",
    "B/G",
    "R/G",
    "R/W",
    "G/W",
    "G/U",
)
_TWOBRID = tuple(f"2/{letter}" for letter in _WUBRG_ORDER)
_COLORLESS_HYBRID = tuple(f"C/{letter}" for letter in _WUBRG_ORDER)
_PHYREXIAN = tuple(f"{letter}/P" for letter in _WUBRG_ORDER)
_PHYREXIAN_HYBRID = tuple(f"{pair}/P" for pair in _HYBRID_PAIRS)

# Single-character codes plus generic numbers: one symbol, no slash.
SIMPLE_CODES: frozenset[str] = frozenset(
    {*"WUBRGCXS", *(str(n) for n in range(0, 21))}
)
# Slashed codes: two or three parts, order fixed by Scryfall.
COMPOUND_CODES: frozenset[str] = frozenset(
    (*_HYBRID_PAIRS, *_TWOBRID, *_COLORLESS_HYBRID, *_PHYREXIAN, *_PHYREXIAN_HYBRID)
)
# Filenames under resources/card-symbols/{asset}.svg (no braces, no slashes).
SYMBOL_CODES: frozenset[str] = SIMPLE_CODES | COMPOUND_CODES

# A compound is identified by its parts, so ``{U/W}`` resolves to ``W/U``.
_COMPOUND_BY_PARTS: dict[frozenset[str], str] = {
    frozenset(code.split("/")): code for code in COMPOUND_CODES
}

_SYMBOL_RE = re.compile(r"\{([^}]+)\}")


def symbol_asset_name(code: str) -> str:
    """Asset stem for a code (``W/U`` → ``WU``); Scryfall names them this way."""
    return code.replace("/", "")


def _normalize_compound(text: str) -> str:
    parts = tuple(part.strip().upper() for part in text.split("/") if part.strip())
    canonical = _COMPOUND_BY_PARTS.get(frozenset(parts))
    if canonical is not None and len(set(parts)) == len(parts):
        return canonical
    return "/".join(parts)


def normalize_symbol_code(inner: str) -> str:
    """Map a brace interior (``G``, ``w``, ``10``, ``u/w``) to a resource code."""
    text = inner.strip()
    if not text:
        return text
    if "/" in text:
        return _normalize_compound(text)
    if text.isdigit() or (text[0].isdigit() and text.replace(".", "", 1).isdigit()):
        # Half-mana and similar stay as-is; only exact ints 0–20 are bundled.
        try:
            as_int = int(float(text))
            if float(text) == as_int:
                return str(as_int)
        except ValueError:
            pass
        return text
    return text.upper()


def is_symbol_code(code: str) -> bool:
    return code in SYMBOL_CODES


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
        if is_symbol_code(code):
            out.append(code)
    return tuple(out)


def mana_cost_codes(mana_cost: str | None) -> tuple[str, ...]:
    """Bundled codes from a Scryfall ``mana_cost`` string, in print order."""
    return renderable_codes(parse_brace_symbols(mana_cost))


def mana_cost_text(mana_cost: str | None) -> str:
    """Brace text without braces (``{2}{W/U}`` → ``2 W/U``) for tooltips/fallback."""
    symbols = parse_brace_symbols(mana_cost)
    if not symbols:
        return ""
    return " ".join(normalize_symbol_code(inner) or inner for inner in symbols)
