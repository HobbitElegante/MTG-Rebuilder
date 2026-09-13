"""Compact inventory field list shown under the card preview."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFormLayout, QLabel, QSizePolicy, QWidget

from mtg_rebuilder.algorithms.mana_symbols import color_identity_codes
from mtg_rebuilder.i18n import Translator
from mtg_rebuilder.services.browse_service import InventorySummaryRow
from mtg_rebuilder.ui.inventory_display import format_inventory_detail_lines
from mtg_rebuilder.ui.mana_icons import symbols_rich_html


class InventoryCardDetails(QWidget):
    """Read-only label/value list for the selected inventory row."""

    def __init__(
        self,
        translator: Translator,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._translator = translator
        self._track_editions = False
        self._row: InventorySummaryRow | None = None
        self._form = QFormLayout(self)
        self._form.setContentsMargins(0, 8, 0, 0)
        self._form.setHorizontalSpacing(12)
        self._form.setVerticalSpacing(4)
        self._form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

    def set_track_editions(self, enabled: bool) -> None:
        self._track_editions = enabled
        self._rebuild()

    def set_row(self, row: InventorySummaryRow | None) -> None:
        self._row = row
        self._rebuild()

    def clear(self) -> None:
        self.set_row(None)

    def retranslate(self) -> None:
        self._rebuild()

    def _rebuild(self) -> None:
        while self._form.rowCount():
            self._form.removeRow(0)
        if self._row is None:
            empty = QLabel(self._translator.t("inventory.view.details_empty"))
            empty.setWordWrap(True)
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._form.addRow(empty)
            return
        color_label = self._translator.t("inventory.table.color")
        for label, value in format_inventory_detail_lines(
            self._row,
            self._translator,
            track_editions=self._track_editions,
        ):
            value_label = QLabel()
            value_label.setWordWrap(True)
            value_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            if label == color_label:
                codes = color_identity_codes(self._row.color_identity)
                if codes:
                    value_label.setTextFormat(Qt.TextFormat.RichText)
                    value_label.setText(symbols_rich_html(codes, size=14))
                    value_label.setToolTip(value)
                else:
                    value_label.setText(value)
            else:
                value_label.setText(value)
            self._form.addRow(f"{label}:", value_label)
