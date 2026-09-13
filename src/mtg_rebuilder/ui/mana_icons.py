"""Render bundled Scryfall card-symbol SVGs to QPixmap / QIcon.

Assets live in ``mtg_rebuilder/resources/card-symbols/`` (tier B: WUBRGC,
0–15, X). Parsing stays in ``algorithms.mana_symbols`` so CI can test it
without Qt.
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
    is_tier_b_code,
    mana_cost_codes,
    normalize_symbol_code,
)
from mtg_rebuilder.resources import CARD_SYMBOLS_DIR

DEFAULT_SYMBOL_SIZE = 16


def symbol_svg_path(code: str) -> Path | None:
    """Filesystem path for a tier-B code, or ``None`` if missing/unknown."""
    normalized = normalize_symbol_code(code)
    if not is_tier_b_code(normalized):
        return None
    path = CARD_SYMBOLS_DIR / f"{normalized}.svg"
    return path if path.is_file() else None


@lru_cache(maxsize=128)
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


def color_identity_pixmap(
    color_identity: str | None, *, size: int = DEFAULT_SYMBOL_SIZE
) -> QPixmap | None:
    return compose_symbol_pixmap(color_identity_codes(color_identity), size=size)


def mana_cost_pixmap(
    mana_cost: str | None, *, size: int = DEFAULT_SYMBOL_SIZE
) -> QPixmap | None:
    return compose_symbol_pixmap(mana_cost_codes(mana_cost), size=size)


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
