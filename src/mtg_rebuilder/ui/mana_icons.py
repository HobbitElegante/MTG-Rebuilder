"""Render bundled Scryfall card-symbol SVGs to QPixmap / QIcon.

Assets live in ``mtg_rebuilder/resources/card-symbols/`` (WUBRGC, generic
0–20, X, snow, hybrids and Phyrexian). Parsing stays in
``algorithms.mana_symbols`` so CI can test it without Qt.
"""

from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from mtg_rebuilder.algorithms.mana_symbols import (
    color_identity_codes,
    is_symbol_code,
    mana_cost_codes,
    normalize_symbol_code,
    parse_brace_symbols,
    symbol_asset_name,
)
from mtg_rebuilder.resources import CARD_SYMBOLS_DIR

DEFAULT_SYMBOL_SIZE = 16


def symbol_svg_path(code: str) -> Path | None:
    """Filesystem path for a bundled code, or ``None`` if missing/unknown."""
    normalized = normalize_symbol_code(code)
    if not is_symbol_code(normalized):
        return None
    path = CARD_SYMBOLS_DIR / f"{symbol_asset_name(normalized)}.svg"
    return path if path.is_file() else None


@lru_cache(maxsize=256)
def load_symbol_pixmap(code: str, size: int = DEFAULT_SYMBOL_SIZE) -> QPixmap | None:
    path = symbol_svg_path(code)
    if path is None or size <= 0:
        return None
    renderer = QSvgRenderer(str(path))
    if not renderer.isValid():
        return None
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return pixmap


def symbol_icon(code: str, size: int = DEFAULT_SYMBOL_SIZE) -> QIcon:
    pixmap = load_symbol_pixmap(code, size)
    return QIcon(pixmap) if pixmap is not None else QIcon()


def compose_symbol_pixmap(
    codes: Sequence[str],
    *,
    size: int = DEFAULT_SYMBOL_SIZE,
    gap: int = 1,
) -> QPixmap | None:
    """Side-by-side strip of symbols; ``None`` when nothing renderable."""
    pixmaps = [
        pixmap
        for code in codes
        if (pixmap := load_symbol_pixmap(code, size)) is not None
    ]
    if not pixmaps:
        return None
    width = size * len(pixmaps) + gap * (len(pixmaps) - 1)
    strip = QPixmap(width, size)
    strip.fill(Qt.GlobalColor.transparent)
    painter = QPainter(strip)
    x = 0
    for pixmap in pixmaps:
        painter.drawPixmap(x, 0, pixmap)
        x += size + gap
    painter.end()
    return strip


# Both strips are cached: Inventory composes one per row (~1.9k) but the
# collection only holds a few hundred distinct costs and 32 identities.
@lru_cache(maxsize=64)
def color_identity_pixmap(
    color_identity: str | None, *, size: int = DEFAULT_SYMBOL_SIZE
) -> QPixmap | None:
    return compose_symbol_pixmap(color_identity_codes(color_identity), size=size)


@lru_cache(maxsize=512)
def mana_cost_pixmap(
    mana_cost: str | None, *, size: int = DEFAULT_SYMBOL_SIZE
) -> QPixmap | None:
    """Strip for a whole cost, or ``None`` if any symbol is outside the bundle.

    All-or-nothing on purpose: a partial strip would read as a cheaper cost,
    so callers fall back to the brace text instead.
    """
    inners = parse_brace_symbols(mana_cost)
    codes = mana_cost_codes(mana_cost)
    if len(codes) != len(inners):
        return None
    return compose_symbol_pixmap(codes, size=size)


def symbols_rich_html(
    codes: Sequence[str],
    *,
    size: int = 14,
    separator: str = "",
) -> str:
    """``<img>`` tags for QLabel rich text (absolute ``file://`` paths)."""
    parts: list[str] = []
    for code in codes:
        path = symbol_svg_path(code)
        if path is None:
            parts.append(code)
            continue
        parts.append(
            f'<img src="{path.as_uri()}" width="{size}" height="{size}">'
        )
    return separator.join(parts)


def mana_cost_rich_html(mana_cost: str | None, *, size: int = 14) -> str:
    """Cost for QLabel rich text; symbols we don't ship stay as their code."""
    codes = [
        normalize_symbol_code(inner) for inner in parse_brace_symbols(mana_cost)
    ]
    return symbols_rich_html(codes, size=size)


def pips_rich_html(
    color_pips: Sequence[tuple[str, int]], *, size: int = 14
) -> str:
    """``🟢 3 · 🔵 1`` style row using bundled SVGs."""
    chunks: list[str] = []
    for letter, qty in color_pips:
        path = symbol_svg_path(letter)
        if path is None:
            chunks.append(f"{letter}&nbsp;{qty}")
        else:
            chunks.append(
                f'<img src="{path.as_uri()}" width="{size}" height="{size}">'
                f"&nbsp;{qty}"
            )
    return " · ".join(chunks)
