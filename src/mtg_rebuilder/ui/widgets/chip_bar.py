"""Wrapping row of removable chips, used for active filters and picker queues.

Chips replaced the old "select a row, then press Remove" lists: the removal
affordance now lives on the item itself, so there is no state where the button
is pressable but does nothing.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import NamedTuple

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLayoutItem,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QWidget,
)

CHIP_SPACING = 6
REMOVE_GLYPH = "✕"


class Chip(NamedTuple):
    key: object
    label: str
    tooltip: str = ""


class FlowLayout(QLayout):
    """Left-to-right layout that wraps to a new line instead of clipping."""

    def __init__(self, parent: QWidget | None = None, spacing: int = CHIP_SPACING):
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(spacing)

    def addItem(self, item: QLayoutItem) -> None:  # noqa: N802 (Qt naming)
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:  # noqa: N802 (Qt naming)
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int) -> QLayoutItem | None:  # noqa: N802 (Qt naming)
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self) -> Qt.Orientations:  # noqa: N802 (Qt naming)
        return Qt.Orientations(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802 (Qt naming)
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802 (Qt naming)
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802 (Qt naming)
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt naming)
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802 (Qt naming)
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QSize(
            margins.left() + margins.right(), margins.top() + margins.bottom()
        )

    def _do_layout(self, rect: QRect, *, test_only: bool) -> int:
        margins = self.contentsMargins()
        effective = rect.adjusted(
            margins.left(), margins.top(), -margins.right(), -margins.bottom()
        )
        x = effective.x()
        y = effective.y()
        line_height = 0
        space = self.spacing()
        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + space
            if next_x - space > effective.right() and line_height > 0:
                x = effective.x()
                y = y + line_height + space
                next_x = x + hint.width() + space
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + margins.bottom()


class ChipBar(QWidget):
    """Chips with a ✕ each, plus an optional trailing "clear all" button."""

    chip_removed = Signal(object)
    cleared = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._chips: list[Chip] = []
        self._remove_tooltip = ""
        self._clear_text = ""
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self._layout = FlowLayout(self)
        self._clear_button = QPushButton(self)
        self._clear_button.setFlat(True)
        self._clear_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._clear_button.clicked.connect(self.cleared.emit)
        self._clear_button.hide()

    def set_texts(self, *, remove_tooltip: str = "", clear_text: str = "") -> None:
        """Retranslate the ✕ tooltip and the optional clear-all label."""
        self._remove_tooltip = remove_tooltip
        self._clear_text = clear_text
        self._clear_button.setText(clear_text)
        self.set_chips(self._chips)

    def chips(self) -> tuple[Chip, ...]:
        return tuple(self._chips)

    def set_chips(self, chips: Sequence[Chip]) -> None:
        self._chips = list(chips)
        self._clear_widgets()
        for chip in self._chips:
            self._layout.addWidget(self._build_chip(chip))
        if self._chips and self._clear_text:
            self._clear_button.setParent(self)
            self._layout.addWidget(self._clear_button)
            self._clear_button.show()
        else:
            self._clear_button.hide()
        self.setVisible(bool(self._chips))
        self.updateGeometry()

    def _clear_widgets(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is None:
                continue
            # The clear button is reused across rebuilds, so it is only unparented.
            if widget is self._clear_button:
                widget.hide()
                widget.setParent(None)
            else:
                widget.deleteLater()

    def _build_chip(self, chip: Chip) -> QWidget:
        frame = QFrame(self)
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        row = QHBoxLayout(frame)
        row.setContentsMargins(8, 2, 4, 2)
        row.setSpacing(4)

        label = QLabel(chip.label, frame)
        label.setTextFormat(Qt.TextFormat.PlainText)
        row.addWidget(label)

        remove = QToolButton(frame)
        remove.setText(REMOVE_GLYPH)
        remove.setAutoRaise(True)
        remove.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        remove.setCursor(Qt.CursorShape.PointingHandCursor)
        remove.setToolTip(self._remove_tooltip)
        remove.clicked.connect(lambda: self.chip_removed.emit(chip.key))
        row.addWidget(remove)

        tooltip = chip.tooltip or chip.label
        frame.setToolTip(tooltip)
        label.setToolTip(tooltip)
        return frame
