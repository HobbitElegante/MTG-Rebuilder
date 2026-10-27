"""Scryfall logo icon — painted with QPainter (no QtSvg).

The original brand path is extremely dense; rendering it via QSvgRenderer on
toggle was freezing the UI on some systems. A simplified seal is enough to
read as “Scryfall” and swaps instantly between muted / active.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

_COLOR_INACTIVE = QColor("#94a3b8")
_COLOR_ACTIVE = QColor("#0f766e")
_CHIP_ACTIVE = QColor("#ccfbf1")
_CHIP_BORDER = QColor("#5eead4")

_ICON_CACHE: dict[tuple[int, object], QIcon] = {}


def _draw_seal(painter: QPainter, bound: QRectF, color: QColor) -> None:
    """Simplified circular seal inspired by the Scryfall mark."""
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawEllipse(bound)

    # Inner crescent / spiral hint (light cutouts).
    inset = bound.adjusted(
        bound.width() * 0.18,
        bound.height() * 0.18,
        -bound.width() * 0.18,
        -bound.height() * 0.18,
    )
    painter.setBrush(QColor(255, 255, 255, 230))
    path = QPainterPath()
    path.moveTo(QPointF(inset.center().x(), inset.top()))
    path.quadTo(
        QPointF(inset.left(), inset.center().y()),
        QPointF(inset.center().x(), inset.bottom()),
    )
    path.quadTo(
        QPointF(inset.left() + inset.width() * 0.35, inset.center().y()),
        QPointF(inset.center().x(), inset.top()),
    )
    painter.drawPath(path)

    # Small accent dots along the right (reads as the nested arcs).
    painter.setBrush(QColor(255, 255, 255, 220))
    cx = bound.center().x() + bound.width() * 0.18
    for factor in (0.28, 0.42, 0.56, 0.70):
        y = bound.top() + bound.height() * factor
        r = bound.width() * 0.045
        painter.drawEllipse(QPointF(cx, y), r, r)


def scryfall_icon(size: int = 22, *, active: bool = False) -> QIcon:
    key = (size, active)
    cached = _ICON_CACHE.get(key)
    if cached is not None:
        return cached

    # Slightly larger canvas when active so the chip reads clearly.
    canvas = size + (6 if active else 0)
    pixmap = QPixmap(QSize(canvas, canvas))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    if active:
        painter.setPen(QPen(_CHIP_BORDER, 1.5))
        painter.setBrush(_CHIP_ACTIVE)
        painter.drawEllipse(QRectF(0.75, 0.75, canvas - 1.5, canvas - 1.5))
        margin = 4.0
        color = _COLOR_ACTIVE
    else:
        margin = 1.0
        color = _COLOR_INACTIVE

    seal = QRectF(margin, margin, canvas - 2 * margin, canvas - 2 * margin)
    _draw_seal(painter, seal, color)
    painter.end()

    icon = QIcon(pixmap)
    _ICON_CACHE[key] = icon
    return icon


def _blank(size: int) -> tuple[QPixmap, QPainter]:
    pixmap = QPixmap(QSize(size, size))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    return pixmap, painter


def search_icon(size: int = 22) -> QIcon:
    """Magnifier for the Scryfall run button (reads on light and dark)."""
    key = (size, "search")
    cached = _ICON_CACHE.get(key)
    if cached is not None:
        return cached
    pixmap, painter = _blank(size)
    pen = QPen(_COLOR_ACTIVE, max(2.0, size / 9))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    lens = size * 0.58
    painter.drawEllipse(QRectF(size * 0.12, size * 0.12, lens, lens))
    painter.drawLine(
        QPointF(size * 0.12 + lens * 0.88, size * 0.12 + lens * 0.88),
        QPointF(size * 0.88, size * 0.88),
    )
    painter.end()
    icon = QIcon(pixmap)
    _ICON_CACHE[key] = icon
    return icon


def stop_icon(size: int = 22) -> QIcon:
    """Square stop mark shown on the run button while a search is going."""
    key = (size, "stop")
    cached = _ICON_CACHE.get(key)
    if cached is not None:
        return cached
    pixmap, painter = _blank(size)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(_COLOR_ACTIVE)
    side = size * 0.5
    offset = (size - side) / 2
    painter.drawRoundedRect(QRectF(offset, offset, side, side), 2, 2)
    painter.end()
    icon = QIcon(pixmap)
    _ICON_CACHE[key] = icon
    return icon
