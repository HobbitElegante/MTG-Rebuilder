from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from mtg_rebuilder.algorithms.card_utils import is_scryfall_legality_issue
from mtg_rebuilder.algorithms.format_rules import profile_for
from mtg_rebuilder.config import HOUSE_BANNED_LEGALITY
from mtg_rebuilder.database import get_session
from mtg_rebuilder.i18n import Translator
from mtg_rebuilder.models.enums import DeckCardRole, DeckFormat, DeckStatus
from mtg_rebuilder.services import BrowseService, ImportService, ScryfallService
from mtg_rebuilder.services.browse_service import CardSummary
from mtg_rebuilder.services.deck_export import (
    DeckExportCard,
    ExportFormat,
    format_deck_export,
)
from mtg_rebuilder.services.deck_service import (
    DeckDeleteCardImpact,
    DeckEditLine,
    DeckEditRow,
)
from mtg_rebuilder.services.import_service import (
    DeckListChange,
    DeckListUpdatePreview,
    InventoryListCard,
    TrackableDeckCard,
)
from mtg_rebuilder.ui.combo import configure_data_combo
from mtg_rebuilder.ui.inventory_display import format_card_legality_tooltip
from mtg_rebuilder.ui.widgets.card_preview import (
    CardPreviewPanel,
    build_preview_splitter,
    card_images_enabled,
)

SECONDARY_ROLES: tuple[DeckCardRole, ...] = (
    DeckCardRole.PARTNER,
    DeckCardRole.COMPANION,
    DeckCardRole.BACKGROUND,
)

_ROLE_I18N_KEY: dict[DeckCardRole, str] = {
    DeckCardRole.PARTNER: "decks.role.partner",
    DeckCardRole.COMPANION: "decks.role.companion",
    DeckCardRole.BACKGROUND: "decks.role.background",
}

DECK_FORMAT_I18N: tuple[tuple[DeckFormat, str], ...] = (
    (DeckFormat.COMMANDER, "decks.format.commander"),
    (DeckFormat.OTHER, "decks.format.other"),
)

_QTY_STEPPER_HEADROOM = 99


def populate_deck_format_combo(
    combo: QComboBox,
    translator: Translator,
    *,
    current: DeckFormat = DeckFormat.COMMANDER,
) -> None:
    """Fill ``combo`` with deck format tags; select ``current``."""
    combo.clear()
    for fmt, key in DECK_FORMAT_I18N:
        combo.addItem(translator.t(key), fmt)
    index = combo.findData(current)
    if index >= 0:
        combo.setCurrentIndex(index)


def deck_format_from_combo(combo: QComboBox) -> DeckFormat:
    data = combo.currentData()
    if isinstance(data, DeckFormat):
        return data
    if isinstance(data, str):
        try:
            return DeckFormat(data)
        except ValueError:
            pass
    return DeckFormat.COMMANDER


class CommandZoneFields(QWidget):
    """Commander line edit with optional Partner / Companion / Background."""

    def __init__(
        self,
        translator: Translator,
        *,
        commander_name: str | None = None,
        secondary: tuple[DeckCardRole, str] | None = None,
        labeled: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._translator = translator
        self._labeled = labeled
        self._secondary_role: DeckCardRole | None = None

        root = QFormLayout(self) if labeled else QVBoxLayout(self)
        if isinstance(root, QFormLayout):
            root.setContentsMargins(0, 0, 0, 0)
        else:
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(6)

        commander_row = QWidget()
        commander_layout = QHBoxLayout(commander_row)
        commander_layout.setContentsMargins(0, 0, 0, 0)
        self._commander_input = QLineEdit(commander_name or "")
        self._commander_input.setPlaceholderText(translator.t("decks.commander"))
        self._add_secondary_button = QToolButton()
        self._add_secondary_button.setText("+")
        self._add_secondary_button.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )
        self._add_menu = QMenu(self._add_secondary_button)
        self._add_secondary_button.setMenu(self._add_menu)
        commander_layout.addWidget(self._commander_input, 1)
        commander_layout.addWidget(self._add_secondary_button)

        self._secondary_label = QLabel("")
        secondary_row = QWidget()
        secondary_layout = QHBoxLayout(secondary_row)
        secondary_layout.setContentsMargins(0, 0, 0, 0)
        self._secondary_input = QLineEdit()
        self._remove_secondary_button = QToolButton()
        self._remove_secondary_button.setText("−")
        self._remove_secondary_button.clicked.connect(self._hide_secondary)
        secondary_layout.addWidget(self._secondary_input, 1)
        secondary_layout.addWidget(self._remove_secondary_button)
        self._secondary_field = secondary_row

        if labeled:
            assert isinstance(root, QFormLayout)
            root.addRow(translator.t("decks.details_edit.commander"), commander_row)
            root.addRow(self._secondary_label, self._secondary_field)
        else:
            assert isinstance(root, QVBoxLayout)
            root.addWidget(commander_row)
            secondary_wrap = QWidget()
            wrap_layout = QHBoxLayout(secondary_wrap)
            wrap_layout.setContentsMargins(0, 0, 0, 0)
            wrap_layout.addWidget(self._secondary_label)
            wrap_layout.addWidget(self._secondary_field, 1)
            self._secondary_wrap = secondary_wrap
            root.addWidget(secondary_wrap)

        self._secondary_label.setVisible(False)
        self._secondary_field.setVisible(False)
        if not labeled:
            self._secondary_wrap.setVisible(False)

        self._rebuild_add_menu()
        self.retranslate()

        if secondary is not None:
            role, name = secondary
            self._show_secondary(role, name)

    def retranslate(self) -> None:
        self._commander_input.setPlaceholderText(
            self._translator.t("decks.commander")
        )
        self._add_secondary_button.setToolTip(
            self._translator.t("decks.details_edit.add_secondary")
        )
        self._remove_secondary_button.setToolTip(
            self._translator.t("decks.details_edit.remove_secondary")
        )
        self._rebuild_add_menu()
        if self._secondary_role is not None:
            role_label = self._translator.t(_ROLE_I18N_KEY[self._secondary_role])
            self._secondary_label.setText(role_label)
            self._secondary_input.setPlaceholderText(
                self._translator.t("decks.details_edit.secondary_placeholder").format(
                    role=role_label
                )
            )

    def _rebuild_add_menu(self) -> None:
        self._add_menu.clear()
        for role in SECONDARY_ROLES:
            action = QAction(self._translator.t(_ROLE_I18N_KEY[role]), self._add_menu)
            action.triggered.connect(
                lambda _checked=False, r=role: self._show_secondary(r)
            )
            self._add_menu.addAction(action)

    def commander_name(self) -> str | None:
        text = self._commander_input.text().strip()
        return text or None

    def secondary_role(self) -> DeckCardRole | None:
        return self._secondary_role

    def secondary_name(self) -> str | None:
        if self._secondary_role is None:
            return None
        text = self._secondary_input.text().strip()
        return text or None

    def clear(self) -> None:
        self._commander_input.clear()
        self._hide_secondary()

    def set_commander_name(self, name: str | None) -> None:
        self._commander_input.setText(name or "")

    def set_secondary(self, role: DeckCardRole, name: str) -> None:
        self._show_secondary(role, name)

    def validation_error(self) -> str | None:
        if self._secondary_role is not None and not self.secondary_name():
            return self._translator.t("decks.details_edit.secondary_required").format(
                role=self._translator.t(_ROLE_I18N_KEY[self._secondary_role])
            )
        return None

    def _show_secondary(
        self, role: DeckCardRole, name: str | None = None
    ) -> None:
        self._secondary_role = role
        role_label = self._translator.t(_ROLE_I18N_KEY[role])
        self._secondary_label.setText(role_label)
        self._secondary_input.setPlaceholderText(
            self._translator.t("decks.details_edit.secondary_placeholder").format(
                role=role_label
            )
        )
        if name is not None:
            self._secondary_input.setText(name)
        elif not self._secondary_field.isVisible():
            self._secondary_input.clear()
        self._secondary_label.setVisible(True)
        self._secondary_field.setVisible(True)
        if not self._labeled:
            self._secondary_wrap.setVisible(True)
        self._secondary_input.setFocus()

    def _hide_secondary(self) -> None:
        self._secondary_role = None
        self._secondary_input.clear()
        self._secondary_label.setVisible(False)
        self._secondary_field.setVisible(False)
        if not self._labeled:
            self._secondary_wrap.setVisible(False)


class DeckDetailsDialog(QDialog):
    """Rename a deck and set commander plus optional partner/companion/background."""

    def __init__(
        self,
        translator: Translator,
        deck_name: str,
        commander_name: str | None,
        secondary: tuple[DeckCardRole, str] | None = None,
        parent: QWidget | None = None,
        *,
        deck_format: DeckFormat = DeckFormat.COMMANDER,
    ) -> None:
        super().__init__(parent)
        self._translator = translator
        self.setWindowTitle(translator.t("decks.details_edit.title"))
        self.resize(460, 260)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._name_input = QLineEdit(deck_name)
        self._name_input.setPlaceholderText(translator.t("decks.name"))
        form.addRow(translator.t("decks.name"), self._name_input)

        self._format_combo = QComboBox()
        configure_data_combo(self._format_combo)
        populate_deck_format_combo(
            self._format_combo, translator, current=deck_format
        )
        form.addRow(translator.t("decks.format"), self._format_combo)
        layout.addLayout(form)

        self._command_zone = CommandZoneFields(
            translator,
            commander_name=commander_name,
            secondary=secondary,
            labeled=True,
        )
        layout.addWidget(self._command_zone)

        hint = QLabel(translator.t("decks.details_edit.hint"))
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def deck_name(self) -> str:
        return self._name_input.text().strip()

    def deck_format(self) -> DeckFormat:
        return deck_format_from_combo(self._format_combo)

    def commander_name(self) -> str | None:
        return self._command_zone.commander_name()

    def secondary_role(self) -> DeckCardRole | None:
        return self._command_zone.secondary_role()

    def secondary_name(self) -> str | None:
        return self._command_zone.secondary_name()

    def _accept(self) -> None:
        if not self.deck_name():
            QMessageBox.warning(
                self,
                self._translator.t("common.error"),
                self._translator.t("decks.details_edit.name_required"),
            )
            return
        error = self._command_zone.validation_error()
        if error is not None:
            QMessageBox.warning(
                self,
                self._translator.t("common.error"),
                error,
            )
            return
        self.accept()


class ExportDeckDialog(QDialog):
    """Read-only multi-format text export for copy-paste."""

    _FORMAT_KEYS: tuple[tuple[ExportFormat, str], ...] = (
        (ExportFormat.MTGO, "decks.export.format.mtgo"),
        (ExportFormat.MOXFIELD, "decks.export.format.moxfield"),
        (ExportFormat.ARENA, "decks.export.format.arena"),
        (ExportFormat.ARCHIDEKT, "decks.export.format.archidekt"),
        (ExportFormat.MTGGOLDFISH, "decks.export.format.mtggoldfish"),
    )

    def __init__(
        self,
        translator: Translator,
        deck_name: str,
        cards: list[DeckExportCard],
        parent: QWidget | None = None,
        *,
        initial_format: ExportFormat = ExportFormat.MTGO,
    ) -> None:
        super().__init__(parent)
        self._translator = translator
        self._cards = cards
        self.setWindowTitle(
            translator.t("decks.export.title").format(name=deck_name)
        )
        self.resize(480, 560)

        layout = QVBoxLayout(self)
        self._hint = QLabel(translator.t("decks.export.hint"))
        self._hint.setWordWrap(True)
        layout.addWidget(self._hint)

        format_row = QHBoxLayout()
        self._format_label = QLabel(translator.t("decks.export.format"))
        self._format_combo = QComboBox()
        configure_data_combo(self._format_combo)
        for fmt, key in self._FORMAT_KEYS:
            self._format_combo.addItem(translator.t(key), fmt)
        index = self._format_combo.findData(initial_format)
        if index >= 0:
            self._format_combo.setCurrentIndex(index)
        self._format_combo.currentIndexChanged.connect(self._refresh_text)
        format_row.addWidget(self._format_label)
        format_row.addWidget(self._format_combo, 1)
        layout.addLayout(format_row)

        self._text = QTextEdit()
        self._text.setReadOnly(True)
        layout.addWidget(self._text, 1)

        buttons = QHBoxLayout()
        self._copy_button = QPushButton(translator.t("decks.export.copy"))
        self._copy_button.clicked.connect(self._copy_to_clipboard)
        buttons.addWidget(self._copy_button)
        buttons.addStretch()
        close_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_box.rejected.connect(self.reject)
        buttons.addWidget(close_box)
        layout.addLayout(buttons)

        self._status = QLabel("")
        layout.addWidget(self._status)
        self._refresh_text()

    def _selected_format(self) -> ExportFormat:
        # PySide returns StrEnum userData as plain str.
        data = self._format_combo.currentData()
        try:
            return ExportFormat(data) if data is not None else ExportFormat.MTGO
        except ValueError:
            return ExportFormat.MTGO

    def _refresh_text(self) -> None:
        text = format_deck_export(self._cards, self._selected_format())
        self._text.setPlainText(text)
        self._text.selectAll()
        self._status.setText("")

    def _copy_to_clipboard(self) -> None:
        clipboard = QGuiApplication.clipboard()
        if clipboard is None:
            return
        clipboard.setText(self._text.toPlainText())
        self._status.setText(self._translator.t("decks.export.copied"))
        self._text.selectAll()
        self._text.setFocus()


class DeckListUpdateDialog(QDialog):
    """Confirm replacing a deck list, showing what the update adds and removes."""

    def __init__(
        self,
        translator: Translator,
        deck_name: str,
        preview: DeckListUpdatePreview,
        *,
        armed: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._translator = translator
        self.setWindowTitle(
            translator.t("decks.update.title").format(name=deck_name)
        )
        self.resize(640, 520)

        layout = QVBoxLayout(self)
        summary = QLabel(
            translator.t("decks.update.summary").format(
                before=preview.total_before,
                after=preview.total_after,
            )
        )
        summary.setWordWrap(True)
        layout.addWidget(summary)

        if armed:
            armed_note = QLabel(translator.t("decks.update.armed_warning"))
            armed_note.setWordWrap(True)
            layout.addWidget(armed_note)

        columns = QHBoxLayout()
        columns.addWidget(
            self._build_change_column(
                translator.t("decks.update.added").format(
                    count=len(preview.added)
                ),
                preview.added,
            ),
            1,
        )
        columns.addWidget(
            self._build_change_column(
                translator.t("decks.update.removed").format(
                    count=len(preview.removed)
                ),
                preview.removed,
            ),
            1,
        )
        layout.addLayout(columns, 1)

        if preview.unresolved_lines:
            layout.addWidget(
                QLabel(
                    translator.t("decks.update.unresolved").format(
                        count=len(preview.unresolved_lines)
                    )
                )
            )
            unresolved = QListWidget()
            unresolved.addItems(preview.unresolved_lines)
            unresolved.setMaximumHeight(96)
            layout.addWidget(unresolved)

        if not preview.has_changes:
            layout.addWidget(QLabel(translator.t("decks.update.no_changes")))

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        apply_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        apply_button.setText(translator.t("decks.update.apply"))
        apply_button.setEnabled(preview.has_changes)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _build_change_column(
        self,
        title: str,
        changes: list[DeckListChange],
    ) -> QWidget:
        column = QWidget()
        column_layout = QVBoxLayout(column)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.addWidget(QLabel(title))
        entries = QListWidget()
        entries.addItems([self._format_change(change) for change in changes])
        column_layout.addWidget(entries, 1)
        return column

    @staticmethod
    def _format_change(change: DeckListChange) -> str:
        if change.before == 0:
            return f"+{change.after}  {change.name}"
        if change.after == 0:
            return f"−{change.before}  {change.name}"
        return f"{change.name}: {change.before} → {change.after}"


class QuantityStepper(QWidget):
    """Numeric value with adjacent − / + buttons instead of spinbox arrows."""

    valueChanged = Signal(int)

    def __init__(
        self,
        maximum: int,
        parent: QWidget | None = None,
        *,
        compact: bool = False,
    ) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6 if not compact else 4)

        self._spin = QSpinBox()
        self._spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self._spin.setRange(0, maximum)
        self._spin.setValue(0)
        self._spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._spin.setMinimumWidth(40 if compact else 56)
        layout.addWidget(self._spin, stretch=1)

        button_width = 28 if compact else 36
        self._minus = QPushButton("-")
        self._plus = QPushButton("+")
        for button in (self._minus, self._plus):
            button.setFixedWidth(button_width)
            button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._minus.clicked.connect(self._step_down)
        self._plus.clicked.connect(self._step_up)
        layout.addWidget(self._minus)
        layout.addWidget(self._plus)

        if not compact:
            self.setMinimumWidth(140)

        self._spin.valueChanged.connect(self._on_value_changed)
        self._sync_buttons()

    def value(self) -> int:
        self._spin.interpretText()
        return self._spin.value()

    def setValue(self, value: int) -> None:
        self._spin.interpretText()
        self._spin.setValue(value)

    def setMaximum(self, maximum: int) -> None:
        self._spin.setMaximum(max(0, maximum))
        if self._spin.value() > self._spin.maximum():
            self._spin.setValue(self._spin.maximum())
        self._sync_buttons()

    def maximum(self) -> int:
        return self._spin.maximum()

    def setMinimum(self, minimum: int) -> None:
        self._spin.setMinimum(minimum)
        if self._spin.value() < self._spin.minimum():
            self._spin.setValue(self._spin.minimum())
        self._sync_buttons()

    def _step_down(self) -> None:
        self._spin.interpretText()
        self._spin.stepDown()

    def _step_up(self) -> None:
        self._spin.interpretText()
        self._spin.stepUp()

    def _on_value_changed(self, value: int) -> None:
        self._sync_buttons()
        self.valueChanged.emit(value)

    def _sync_buttons(self) -> None:
        value = self._spin.value()
        self._minus.setEnabled(value > self._spin.minimum())
        self._plus.setEnabled(value < self._spin.maximum())


class ImportStatusDialog(QDialog):
    def __init__(self, translator: Translator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._translator = translator
        self.setWindowTitle(self._translator.t("decks.import.status.title"))
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(self._translator.t("decks.import.status.question")))

        self._armed_radio = QRadioButton(self._translator.t("decks.status.armed"))
        self._dismantled_radio = QRadioButton(
            self._translator.t("decks.status.dismantled")
        )
        self._dismantled_radio.setChecked(True)
        layout.addWidget(self._armed_radio)
        layout.addWidget(self._dismantled_radio)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_status(self) -> DeckStatus:
        if self._armed_radio.isChecked():
            return DeckStatus.ARMED
        return DeckStatus.DISMANTLED


class AvailableCopiesDialog(QDialog):
    def __init__(
        self,
        translator: Translator,
        cards: list[TrackableDeckCard],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._translator = translator
        self._cards = cards
        self._steppers: list[QuantityStepper] = []
        self.setWindowTitle(self._translator.t("decks.import.available.title"))
        self.resize(640, 480)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(self._translator.t("decks.import.available.question")))

        self._table = QTableWidget(len(self._cards), 3)
        self._table.setHorizontalHeaderLabels(
            [
                self._translator.t("browse.cards.name"),
                self._translator.t("decks.import.available.in_list"),
                self._translator.t("decks.import.available.available"),
            ]
        )
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        for row, card in enumerate(self._cards):
            self._table.setItem(row, 0, QTableWidgetItem(card.name))
            in_list_item = QTableWidgetItem(str(card.quantity))
            in_list_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 1, in_list_item)

            stepper = QuantityStepper(card.quantity, compact=True)
            self._steppers.append(stepper)
            self._table.setCellWidget(row, 2, stepper)

        layout.addWidget(self._table)

        actions = QHBoxLayout()
        all_button = QPushButton(self._translator.t("decks.import.available.all"))
        all_button.clicked.connect(self._mark_all_available)
        actions.addWidget(all_button)
        actions.addStretch()
        layout.addLayout(actions)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _mark_all_available(self) -> None:
        for stepper, card in zip(self._steppers, self._cards, strict=True):
            stepper.setValue(card.quantity)

    def quantities(self) -> dict[str, int]:
        return {
            card.oracle_id: stepper.value()
            for card, stepper in zip(self._cards, self._steppers, strict=True)
            if stepper.value() > 0
        }


@dataclass
class EditableInventoryListLine:
    oracle_id: str
    name: str
    list_quantity: int
    add_quantity: int
    set_code: str | None = None


class AddInventoryListDialog(QDialog):
    """Review a MTGO list: edit quantities for free inventory, show unresolved lines."""

    def __init__(
        self,
        translator: Translator,
        identified: list[InventoryListCard],
        unresolved_lines: list[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._translator = translator
        self._lines = [
            EditableInventoryListLine(
                oracle_id=card.oracle_id,
                name=card.name,
                list_quantity=card.list_quantity,
                add_quantity=min(1, card.list_quantity),
                set_code=card.set_code,
            )
            for card in identified
        ]
        self._unresolved_lines = list(unresolved_lines)
        self._qty_steppers: list[QuantityStepper] = []
        self.setWindowTitle(self._translator.t("inventory.add_list.title"))
        self._preview = (
            CardPreviewPanel(self._translator, self) if card_images_enabled() else None
        )
        self.resize(1280 if self._preview is not None else 1000, 620)
        self._build_ui()
        self._rebuild_table()
        self._rebuild_unresolved()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        panes = QHBoxLayout()

        left = QVBoxLayout()
        left.addWidget(QLabel(self._translator.t("inventory.add_list.identified")))
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            [
                self._translator.t("browse.cards.name"),
                self._translator.t("decks.import.available.in_list"),
                self._translator.t("inventory.add_list.add"),
                self._translator.t("decks.edit.replace"),
                self._translator.t("inventory.add_list.remove"),
            ]
        )
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.currentCellChanged.connect(
            lambda row, *_: self._on_row_selected(row)
        )
        left.addWidget(self._table)
        panes.addLayout(left, stretch=3)

        if self._preview is not None:
            preview_column = QVBoxLayout()
            preview_column.addWidget(self._preview)
            panes.addLayout(preview_column, stretch=1)

        right = QVBoxLayout()
        right.addWidget(QLabel(self._translator.t("inventory.add_list.unresolved")))
        hint = QLabel(self._translator.t("inventory.add_list.unresolved.hint"))
        hint.setWordWrap(True)
        right.addWidget(hint)
        self._unresolved_table = QTableWidget(0, 3)
        self._unresolved_table.setHorizontalHeaderLabels(
            [
                self._translator.t("inventory.add_list.unresolved.line"),
                self._translator.t("inventory.add_list.recheck"),
                self._translator.t("inventory.add_list.remove"),
            ]
        )
        unresolved_header = self._unresolved_table.horizontalHeader()
        unresolved_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        unresolved_header.setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        unresolved_header.setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self._unresolved_table.setEditTriggers(
            QTableWidget.EditTrigger.DoubleClicked
            | QTableWidget.EditTrigger.EditKeyPressed
            | QTableWidget.EditTrigger.SelectedClicked
        )
        right.addWidget(self._unresolved_table)
        panes.addLayout(right, stretch=2)

        root.addLayout(panes)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok is not None:
            ok.setText(self._translator.t("inventory.add_list.confirm"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _on_row_selected(self, row: int) -> None:
        if self._preview is None:
            return
        if row < 0 or row >= len(self._lines):
            self._preview.clear()
            return
        line = self._lines[row]
        self._preview.set_card(line.oracle_id, line.name)

    def _rebuild_table(self) -> None:
        self._qty_steppers = []
        self._table.setRowCount(len(self._lines))
        for row, line in enumerate(self._lines):
            self._table.setItem(row, 0, QTableWidgetItem(line.name))

            in_list = QTableWidgetItem(str(line.list_quantity))
            in_list.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 1, in_list)

            stepper = QuantityStepper(line.list_quantity, compact=True)
            stepper.setMinimum(0)
            stepper.blockSignals(True)
            stepper.setValue(min(line.add_quantity, line.list_quantity))
            stepper.blockSignals(False)
            stepper.valueChanged.connect(
                lambda value, index=row: self._on_qty_changed(index, value)
            )
            self._qty_steppers.append(stepper)
            self._table.setCellWidget(row, 2, stepper)

            replace = QPushButton(self._translator.t("decks.edit.replace"))
            replace.clicked.connect(
                lambda _checked=False, index=row: self._replace_card(index)
            )
            self._table.setCellWidget(row, 3, replace)

            remove = QPushButton(self._translator.t("inventory.add_list.remove"))
            remove.clicked.connect(
                lambda _checked=False, index=row: self._remove_card(index)
            )
            self._table.setCellWidget(row, 4, remove)

    def _rebuild_unresolved(self) -> None:
        self._unresolved_table.setRowCount(len(self._unresolved_lines))
        for row, line in enumerate(self._unresolved_lines):
            item = QTableWidgetItem(line)
            item.setFlags(
                Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsEditable
            )
            self._unresolved_table.setItem(row, 0, item)

            recheck = QPushButton(self._translator.t("inventory.add_list.recheck"))
            recheck.clicked.connect(
                lambda _checked=False, index=row: self._recheck_unresolved(index)
            )
            self._unresolved_table.setCellWidget(row, 1, recheck)

            remove = QPushButton(self._translator.t("inventory.add_list.remove"))
            remove.clicked.connect(
                lambda _checked=False, index=row: self._remove_unresolved(index)
            )
            self._unresolved_table.setCellWidget(row, 2, remove)

    def _sync_unresolved_from_table(self) -> None:
        for row in range(self._unresolved_table.rowCount()):
            item = self._unresolved_table.item(row, 0)
            if item is None or row >= len(self._unresolved_lines):
                continue
            self._unresolved_lines[row] = item.text().strip()

    def _on_qty_changed(self, index: int, value: int) -> None:
        if index < 0 or index >= len(self._lines):
            return
        if value <= 0:
            del self._lines[index]
            self._rebuild_table()
            return
        self._lines[index].add_quantity = value

    def _remove_card(self, index: int) -> None:
        if index < 0 or index >= len(self._lines):
            return
        del self._lines[index]
        self._rebuild_table()

    def _remove_unresolved(self, index: int) -> None:
        self._sync_unresolved_from_table()
        if index < 0 or index >= len(self._unresolved_lines):
            return
        del self._unresolved_lines[index]
        self._rebuild_unresolved()

    def _merge_identified(self, card: InventoryListCard) -> None:
        for line in self._lines:
            if line.oracle_id == card.oracle_id:
                line.list_quantity += card.list_quantity
                line.add_quantity = min(
                    max(line.add_quantity, 1),
                    line.list_quantity,
                )
                return
        self._lines.append(
            EditableInventoryListLine(
                oracle_id=card.oracle_id,
                name=card.name,
                list_quantity=card.list_quantity,
                add_quantity=min(1, card.list_quantity),
                set_code=card.set_code,
            )
        )
        self._lines.sort(key=lambda entry: entry.name.casefold())

    def _recheck_unresolved(self, index: int) -> None:
        self._sync_unresolved_from_table()
        if index < 0 or index >= len(self._unresolved_lines):
            return
        text = self._unresolved_lines[index].strip()
        if not text:
            del self._unresolved_lines[index]
            self._rebuild_unresolved()
            return

        try:
            with get_session() as session:
                scryfall = ScryfallService(session)
                try:
                    preview = ImportService(
                        session, scryfall
                    ).preview_inventory_list(text)
                finally:
                    scryfall.close()
        except Exception as exc:
            QMessageBox.critical(
                self,
                self._translator.t("common.error"),
                str(exc),
            )
            return

        if preview.identified:
            for card in preview.identified:
                self._merge_identified(card)
            del self._unresolved_lines[index]
            # Keep any leftover unresolved fragments from the same recheck.
            for leftover in preview.unresolved_lines:
                self._unresolved_lines.insert(index, leftover)
                index += 1
            self._rebuild_table()
            self._rebuild_unresolved()
            return

        if preview.unresolved_lines:
            self._unresolved_lines[index] = preview.unresolved_lines[0]
            for extra in preview.unresolved_lines[1:]:
                self._unresolved_lines.insert(index + 1, extra)
            self._rebuild_unresolved()
            QMessageBox.information(
                self,
                self._translator.t("inventory.add_list.title"),
                self._translator.t("inventory.add_list.recheck.failed"),
            )
            return

        # Resolved as basic/token (or blank) — drop from unresolved.
        del self._unresolved_lines[index]
        self._rebuild_unresolved()
        QMessageBox.information(
            self,
            self._translator.t("inventory.add_list.title"),
            self._translator.t("inventory.add_list.recheck.skipped"),
        )

    def _replace_card(self, index: int) -> None:
        if index < 0 or index >= len(self._lines):
            return
        line = self._lines[index]
        dialog = CardPickDialog(
            self._translator,
            title=self._translator.t("decks.edit.replace"),
            max_quantity=max(1, line.list_quantity),
            show_available=False,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        result = dialog.result()
        if result is None:
            return
        if result.is_basic_land or result.is_token:
            QMessageBox.warning(
                self,
                self._translator.t("common.error"),
                self._translator.t("inventory.add_list.not_trackable"),
            )
            return
        # Merge into existing row if the replacement is already in the table.
        for other_index, other in enumerate(self._lines):
            if other_index == index:
                continue
            if other.oracle_id == result.oracle_id:
                other.list_quantity += line.list_quantity
                other.add_quantity = min(
                    max(other.add_quantity, line.add_quantity),
                    other.list_quantity,
                )
                del self._lines[index]
                self._rebuild_table()
                return
        line.oracle_id = result.oracle_id
        line.name = result.name
        line.list_quantity = max(line.list_quantity, result.quantity)
        line.add_quantity = min(line.add_quantity, line.list_quantity)
        self._rebuild_table()

    def quantities(self) -> dict[str, int]:
        return {
            line.oracle_id: line.add_quantity
            for line in self._lines
            if line.add_quantity > 0
        }

    def set_codes(self) -> dict[str, str | None]:
        return {
            line.oracle_id: line.set_code
            for line in self._lines
            if line.add_quantity > 0
        }


class DeleteDeckDialog(QDialog):
    def __init__(
        self,
        translator: Translator,
        deck_name: str,
        impacts: list[DeckDeleteCardImpact],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._translator = translator
        self._impacts = impacts
        self._steppers: list[QuantityStepper] = []
        self._remaining_items: list[QTableWidgetItem] = []
        self.setWindowTitle(self._translator.t("decks.delete.confirm.title"))
        self.resize(900, 560)
        self._build_ui(deck_name)

    def _build_ui(self, deck_name: str) -> None:
        layout = QVBoxLayout(self)
        question = QLabel(
            self._translator.t("decks.delete.confirm.question").format(name=deck_name)
        )
        question.setWordWrap(True)
        layout.addWidget(question)
        hint = QLabel(self._translator.t("decks.delete.copies.hint"))
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._table = QTableWidget(len(self._impacts), 5)
        self._table.setHorizontalHeaderLabels(
            [
                self._translator.t("browse.cards.name"),
                self._translator.t("decks.import.available.in_list"),
                self._translator.t("decks.delete.copies.inventory"),
                self._translator.t("decks.delete.copies.remove"),
                self._translator.t("decks.delete.copies.remaining"),
            ]
        )
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setColumnWidth(3, 160)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        for row, impact in enumerate(self._impacts):
            self._table.setItem(row, 0, QTableWidgetItem(impact.name))

            in_list = QTableWidgetItem(str(impact.list_quantity))
            in_list.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 1, in_list)

            inventory = QTableWidgetItem(self._inventory_label(impact))
            inventory.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if impact.assigned_elsewhere > 0:
                inventory.setToolTip(
                    self._translator.t("decks.delete.copies.elsewhere_tip").format(
                        count=impact.assigned_elsewhere
                    )
                )
            self._table.setItem(row, 2, inventory)

            stepper = QuantityStepper(impact.removable_copies)
            stepper.setEnabled(impact.removable_copies > 0)
            stepper.valueChanged.connect(
                lambda _value, index=row: self._update_remaining(index)
            )
            self._steppers.append(stepper)
            self._table.setCellWidget(row, 3, stepper)

            remaining = QTableWidgetItem(str(impact.total_copies))
            remaining.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._remaining_items.append(remaining)
            self._table.setItem(row, 4, remaining)

        layout.addWidget(self._table)

        actions = QHBoxLayout()
        keep_all = QPushButton(self._translator.t("decks.delete.copies.keep_all"))
        keep_all.clicked.connect(self._keep_all_copies)
        remove_all = QPushButton(self._translator.t("decks.delete.copies.remove_all"))
        remove_all.clicked.connect(self._remove_all_copies)
        actions.addWidget(keep_all)
        actions.addWidget(remove_all)
        actions.addStretch()
        layout.addLayout(actions)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setText(self._translator.t("decks.delete_list"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _inventory_label(self, impact: DeckDeleteCardImpact) -> str:
        if impact.assigned_elsewhere <= 0:
            return str(impact.total_copies)
        return self._translator.t("decks.delete.copies.inventory_elsewhere").format(
            total=impact.total_copies,
            elsewhere=impact.assigned_elsewhere,
        )

    def _update_remaining(self, row: int) -> None:
        impact = self._impacts[row]
        remaining = impact.total_copies - self._steppers[row].value()
        self._remaining_items[row].setText(str(remaining))

    def _keep_all_copies(self) -> None:
        for stepper in self._steppers:
            stepper.setValue(0)

    def _remove_all_copies(self) -> None:
        for stepper, impact in zip(self._steppers, self._impacts, strict=True):
            stepper.setValue(impact.removable_copies)

    def removals(self) -> dict[str, int]:
        return {
            impact.oracle_id: stepper.value()
            for impact, stepper in zip(self._impacts, self._steppers, strict=True)
            if stepper.value() > 0
        }


@dataclass
class EditableDeckLine:
    oracle_id: str
    name: str
    quantity: int
    role: DeckCardRole
    is_basic_land: bool
    is_token: bool
    removable_copies: int
    baseline_free: int
    desired_free: int
    commander_legality: str | None = None


@dataclass
class CardPickResult:
    oracle_id: str
    name: str
    quantity: int
    available: int
    is_basic_land: bool
    is_token: bool
    remove_outgoing: int = 0
    commander_legality: str | None = None


class CardPickDialog(QDialog):
    def __init__(
        self,
        translator: Translator,
        *,
        title: str,
        max_quantity: int,
        outgoing: EditableDeckLine | None = None,
        show_available: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._translator = translator
        self._max_quantity = max(1, max_quantity)
        self._outgoing = outgoing
        self._show_available = show_available
        self._results: list[CardSummary] = []
        self.setWindowTitle(title)
        self.resize(880 if card_images_enabled() else 560, 520)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self._search = QLineEdit()
        self._search.setPlaceholderText(self._translator.t("decks.edit.search"))
        self._search.textChanged.connect(self._refresh_results)
        self._search.returnPressed.connect(self._refresh_results)
        layout.addWidget(self._search)

        self._results_list = QListWidget()
        self._results_list.currentRowChanged.connect(
            lambda _row: self._on_result_selected()
        )
        self._preview: CardPreviewPanel | None = None
        if card_images_enabled():
            self._preview = CardPreviewPanel(self._translator)
            layout.addWidget(build_preview_splitter(self._results_list, self._preview))
        else:
            layout.addWidget(self._results_list)

        form = QFormLayout()
        self._qty = QuantityStepper(self._max_quantity)
        self._qty.setMinimum(1)
        default_qty = (
            1
            if self._outgoing is None
            else min(self._outgoing.quantity, self._max_quantity)
        )
        self._qty.setValue(max(1, default_qty))
        form.addRow(self._translator.t("decks.edit.quantity"), self._qty)

        self._available = QuantityStepper(self._max_quantity)
        self._available_label = QLabel(self._translator.t("decks.edit.available"))
        form.addRow(self._available_label, self._available)
        self._qty.valueChanged.connect(self._sync_available_max)
        layout.addLayout(form)
        if not self._show_available:
            self._available.setVisible(False)
            self._available_label.setVisible(False)
            self._available.setValue(0)

        self._remove_outgoing_check: QCheckBox | None = None
        self._remove_outgoing_stepper: QuantityStepper | None = None
        if self._outgoing is not None and not self._outgoing.is_basic_land:
            self._remove_outgoing_check = QCheckBox(
                self._translator.t("decks.edit.remove_outgoing")
            )
            layout.addWidget(self._remove_outgoing_check)
            self._remove_outgoing_stepper = QuantityStepper(
                self._outgoing.removable_copies
            )
            self._remove_outgoing_stepper.setEnabled(False)
            self._remove_outgoing_check.toggled.connect(
                self._remove_outgoing_stepper.setEnabled
            )
            form_out = QFormLayout()
            form_out.addRow(
                self._translator.t("decks.edit.remove_outgoing_qty"),
                self._remove_outgoing_stepper,
            )
            layout.addLayout(form_out)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok is not None:
            ok.setText(self._translator.t("decks.edit.pick"))
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._result: CardPickResult | None = None
        self._sync_available_max()
        self._refresh_results()

    def _on_result_selected(self) -> None:
        self._sync_available_max()
        if self._preview is None:
            return
        card = self._selected_card()
        if card is None:
            self._preview.clear()
        else:
            self._preview.set_card(card.oracle_id, card.name)

    def _sync_available_max(self) -> None:
        qty = self._qty.value()
        self._available.setMaximum(qty)
        selected = self._selected_card()
        unlimited = selected is not None and (
            selected.is_basic_land or selected.is_token
        )
        self._available.setEnabled(not unlimited)
        self._available_label.setEnabled(not unlimited)
        if unlimited:
            self._available.setValue(0)

    def _refresh_results(self) -> None:
        search = self._search.text().strip()
        with get_session() as session:
            cards = BrowseService(session).list_cards(search) if search else []
        self._results = cards[:80]
        self._results_list.clear()
        for card in self._results:
            self._results_list.addItem(card.name)

    def _selected_card(self) -> CardSummary | None:
        row = self._results_list.currentRow()
        if row < 0 or row >= len(self._results):
            return None
        return self._results[row]

    def _accept(self) -> None:
        card = self._selected_card()
        if card is None:
            QMessageBox.warning(
                self,
                self._translator.t("common.error"),
                self._translator.t("decks.edit.no_selection"),
            )
            return
        remove_outgoing = 0
        if (
            self._remove_outgoing_check is not None
            and self._remove_outgoing_check.isChecked()
            and self._remove_outgoing_stepper is not None
        ):
            remove_outgoing = self._remove_outgoing_stepper.value()
        available = 0
        if self._show_available and not (card.is_basic_land or card.is_token):
            available = self._available.value()
        self._result = CardPickResult(
            oracle_id=card.oracle_id,
            name=card.name,
            quantity=self._qty.value(),
            available=available,
            is_basic_land=card.is_basic_land,
            is_token=card.is_token,
            remove_outgoing=remove_outgoing,
            commander_legality=card.commander_legality,
        )
        self.accept()

    def result(self) -> CardPickResult | None:
        return self._result


class DeckEditDialog(QDialog):
    def __init__(
        self,
        translator: Translator,
        deck_name: str,
        rows: list[DeckEditRow],
        parent: QWidget | None = None,
        *,
        house_banned_ids: set[str] | None = None,
        show_legality_warnings: bool = True,
        deck_format: DeckFormat = DeckFormat.COMMANDER,
        title: str | None = None,
        save_label: str | None = None,
        summary_text: str | None = None,
        hint_text: str | None = None,
        armed_warning: str | None = None,
        unresolved_lines: list[str] | None = None,
    ) -> None:
        super().__init__(parent)
        self._translator = translator
        self._house_banned_ids = house_banned_ids or set()
        self._show_legality_warnings = show_legality_warnings
        self._deck_format = deck_format
        self._target_size = profile_for(deck_format).target_size
        self._save_label = save_label
        self._summary_text = summary_text
        self._hint_text = hint_text
        self._armed_warning = armed_warning
        self._unresolved_lines = unresolved_lines or []
        self._lines = [
            EditableDeckLine(
                oracle_id=row.oracle_id,
                name=row.name,
                quantity=row.quantity,
                role=row.role,
                is_basic_land=row.is_basic_land,
                is_token=row.is_token,
                removable_copies=row.removable_copies,
                baseline_free=row.free_copies,
                desired_free=row.free_copies,
                commander_legality=row.commander_legality,
            )
            for row in rows
        ]
        self._remove_copies: dict[str, int] = {}
        self._qty_steppers: list[QuantityStepper] = []
        self._free_steppers: list[QuantityStepper | None] = []
        self.setWindowTitle(
            title or f"{self._translator.t('decks.edit.title')} — {deck_name}"
        )
        self._preview: CardPreviewPanel | None = None
        self.resize(1240 if card_images_enabled() else 960, 620)
        self._build_ui()
        self._rebuild_table()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        if self._summary_text:
            summary = QLabel(self._summary_text)
            summary.setWordWrap(True)
            layout.addWidget(summary)
        if self._armed_warning:
            armed_note = QLabel(self._armed_warning)
            armed_note.setWordWrap(True)
            layout.addWidget(armed_note)
        if self._hint_text:
            hint = QLabel(self._hint_text)
            hint.setWordWrap(True)
            layout.addWidget(hint)
        if self._unresolved_lines:
            layout.addWidget(
                QLabel(
                    self._translator.t("decks.update.unresolved").format(
                        count=len(self._unresolved_lines)
                    )
                )
            )
            unresolved = QListWidget()
            unresolved.addItems(self._unresolved_lines)
            unresolved.setMaximumHeight(96)
            layout.addWidget(unresolved)
        self._total_label = QLabel("")
        self._size_warn_label = QLabel("")
        self._size_warn_label.setVisible(False)
        header_row = QHBoxLayout()
        header_row.addWidget(self._total_label)
        header_row.addWidget(self._size_warn_label)
        header_row.addStretch()
        layout.addLayout(header_row)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(
            [
                self._translator.t("browse.cards.name"),
                self._translator.t("decks.import.available.in_list"),
                self._translator.t("decks.edit.free"),
                self._translator.t("decks.edit.replace"),
            ]
        )
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setColumnWidth(1, 160)
        self._table.setColumnWidth(2, 160)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._table.currentCellChanged.connect(
            lambda row, *_: self._on_row_selected(row)
        )
        if card_images_enabled():
            self._preview = CardPreviewPanel(self._translator)
            splitter = build_preview_splitter(self._table, self._preview)
            splitter.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
            layout.addWidget(splitter, 1)
        else:
            layout.addWidget(self._table, 1)

        actions = QHBoxLayout()
        self._add_button = QPushButton(self._translator.t("decks.edit.add"))
        self._add_button.clicked.connect(self._add_card)
        actions.addWidget(self._add_button)
        actions.addStretch()
        layout.addLayout(actions)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        save_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        if save_button is not None:
            save_button.setText(
                self._save_label or self._translator.t("decks.edit.save")
            )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_row_selected(self, row: int) -> None:
        if self._preview is None:
            return
        if row < 0 or row >= len(self._lines):
            self._preview.clear()
            return
        line = self._lines[row]
        self._preview.set_card(line.oracle_id, line.name)

    def _counted_total(self) -> int:
        """List size for format rules (Companion excluded, same as commander_rules)."""
        return sum(
            line.quantity
            for line in self._lines
            if line.role != DeckCardRole.COMPANION
        )

    def _line_display_legality(self, line: EditableDeckLine) -> str | None:
        if line.oracle_id in self._house_banned_ids:
            return HOUSE_BANNED_LEGALITY
        if self._show_legality_warnings and is_scryfall_legality_issue(
            line.commander_legality
        ):
            return line.commander_legality
        return None

    def _line_has_warning(self, line: EditableDeckLine) -> bool:
        return self._line_display_legality(line) is not None

    def _line_warning_tooltip(self, line: EditableDeckLine) -> str:
        legality = self._line_display_legality(line)
        return format_card_legality_tooltip(line.name, legality, self._translator)

    def _update_header(self) -> None:
        current = self._counted_total()
        target = self._target_size
        if target is None:
            self._total_label.setText(
                self._translator.t("decks.edit.total_only").format(current=current)
            )
            self._size_warn_label.clear()
            self._size_warn_label.setVisible(False)
            self._size_warn_label.setToolTip("")
        else:
            self._total_label.setText(
                self._translator.t("decks.edit.total").format(
                    current=current,
                    target=target,
                )
            )
            mismatched = current != target
            self._size_warn_label.setVisible(mismatched)
            if mismatched:
                self._size_warn_label.setText(
                    self._translator.t("decks.legality.warning")
                )
                self._size_warn_label.setToolTip(
                    self._translator.t("decks.edit.size_mismatch").format(
                        current=current,
                        target=target,
                    )
                )
            else:
                self._size_warn_label.clear()
                self._size_warn_label.setToolTip("")
        self._add_button.setEnabled(True)

    def _rebuild_table(self) -> None:
        self._qty_steppers.clear()
        self._free_steppers.clear()
        self._table.setRowCount(len(self._lines))
        for row, line in enumerate(self._lines):
            name_cell = QWidget()
            name_layout = QHBoxLayout(name_cell)
            name_layout.setContentsMargins(6, 0, 6, 0)
            name_layout.setSpacing(4)
            name_label = QLabel(line.name)
            name_label.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
            )
            name_layout.addWidget(name_label, 1)
            if self._line_has_warning(line):
                warn = QLabel(self._translator.t("decks.legality.warning"))
                warn.setToolTip(self._line_warning_tooltip(line))
                name_layout.addWidget(
                    warn, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
            self._table.setCellWidget(row, 0, name_cell)

            stepper = QuantityStepper(
                max(line.quantity + _QTY_STEPPER_HEADROOM, line.quantity, 1)
            )
            stepper.setMinimum(0)
            stepper.setMaximum(max(line.quantity + _QTY_STEPPER_HEADROOM, line.quantity))
            stepper.setValue(line.quantity)
            stepper.valueChanged.connect(
                lambda value, index=row: self._on_qty_changed(index, value)
            )
            self._qty_steppers.append(stepper)
            self._table.setCellWidget(row, 1, stepper)

            if line.is_basic_land or line.is_token:
                free_item = QTableWidgetItem("—")
                free_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row, 2, free_item)
                self._free_steppers.append(None)
            else:
                free_stepper = QuantityStepper(
                    max(line.desired_free + _QTY_STEPPER_HEADROOM, _QTY_STEPPER_HEADROOM)
                )
                free_stepper.setMinimum(0)
                free_stepper.setMaximum(
                    max(line.desired_free + _QTY_STEPPER_HEADROOM, _QTY_STEPPER_HEADROOM)
                )
                free_stepper.setValue(line.desired_free)
                free_stepper.valueChanged.connect(
                    lambda value, index=row: self._on_free_changed(index, value)
                )
                self._free_steppers.append(free_stepper)
                self._table.setCellWidget(row, 2, free_stepper)

            replace = QPushButton(self._translator.t("decks.edit.replace"))
            replace.clicked.connect(lambda _checked=False, index=row: self._replace_card(index))
            self._table.setCellWidget(row, 3, replace)

        self._update_header()

    def _on_free_changed(self, index: int, value: int) -> None:
        if index < 0 or index >= len(self._lines):
            return
        line = self._lines[index]
        if line.is_basic_land or line.is_token:
            return
        line.desired_free = value
        stepper = self._free_steppers[index]
        if stepper is not None and value >= stepper.maximum() - 5:
            stepper.setMaximum(value + _QTY_STEPPER_HEADROOM)

    def _on_qty_changed(self, index: int, value: int) -> None:
        if index < 0 or index >= len(self._lines):
            return
        line = self._lines[index]
        if value <= 0:
            del self._lines[index]
            self._rebuild_table()
            return
        line.quantity = value
        stepper = self._qty_steppers[index]
        if value >= stepper.maximum() - 5:
            stepper.setMaximum(value + _QTY_STEPPER_HEADROOM)
        self._update_header()

    def _add_card(self) -> None:
        dialog = CardPickDialog(
            self._translator,
            title=self._translator.t("decks.edit.add.title"),
            max_quantity=_QTY_STEPPER_HEADROOM,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        picked = dialog.result()
        if picked is None:
            return
        self._lines.append(
            EditableDeckLine(
                oracle_id=picked.oracle_id,
                name=picked.name,
                quantity=picked.quantity,
                role=DeckCardRole.MAIN,
                is_basic_land=picked.is_basic_land,
                is_token=picked.is_token,
                removable_copies=0,
                baseline_free=0,
                desired_free=picked.available,
                commander_legality=picked.commander_legality,
            )
        )
        self._rebuild_table()

    def _replace_card(self, index: int) -> None:
        if index < 0 or index >= len(self._lines):
            return
        outgoing = self._lines[index]
        dialog = CardPickDialog(
            self._translator,
            title=self._translator.t("decks.edit.replace.title"),
            max_quantity=outgoing.quantity,
            outgoing=outgoing,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        picked = dialog.result()
        if picked is None:
            return
        if picked.remove_outgoing > 0:
            self._remove_copies[outgoing.oracle_id] = (
                self._remove_copies.get(outgoing.oracle_id, 0) + picked.remove_outgoing
            )
        self._lines[index] = EditableDeckLine(
            oracle_id=picked.oracle_id,
            name=picked.name,
            quantity=picked.quantity,
            role=outgoing.role,
            is_basic_land=picked.is_basic_land,
            is_token=picked.is_token,
            removable_copies=0,
            baseline_free=0,
            desired_free=picked.available,
            commander_legality=picked.commander_legality,
        )
        self._rebuild_table()

    def edit_lines(self) -> list[DeckEditLine]:
        return [
            DeckEditLine(
                oracle_id=line.oracle_id,
                quantity=line.quantity,
                role=line.role,
            )
            for line in self._lines
            if line.quantity > 0
        ]

    def create_free_copies(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for line in self._lines:
            if line.is_basic_land or line.is_token:
                continue
            delta = line.desired_free - line.baseline_free
            if delta > 0:
                result[line.oracle_id] = result.get(line.oracle_id, 0) + delta
        return result

    def remove_copies(self) -> dict[str, int]:
        result = dict(self._remove_copies)
        for line in self._lines:
            if line.is_basic_land or line.is_token:
                continue
            delta = line.desired_free - line.baseline_free
            if delta < 0:
                result[line.oracle_id] = result.get(line.oracle_id, 0) + (-delta)
        return result
