"""Inventory filter dialog (availability / type / subtype / decks / colors / rarity / mana value)."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction, QIcon, QShowEvent
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QCheckBox,
    QComboBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from mtg_rebuilder.algorithms.inventory_filters import (
    CARD_TYPE_OPTIONS,
    CMC_OPS,
    RARITY_CODES,
    CmcCondition,
    InventoryFilterState,
    WUBRG,
)
from mtg_rebuilder.i18n import Translator
from mtg_rebuilder.ui.combo import (
    SEARCHABLE_COMBO_CONTENTS_LENGTH,
    configure_data_combo,
)

# Type checkboxes per row; 3 keeps the longest label ("Planeswalker") readable
# at the dialog's minimum width.
TYPE_COLUMNS = 3
# Share of the screen the dialog may take before its content starts scrolling.
MAX_HEIGHT_RATIO = 0.85
# Selected types/decks lists grow with their content up to this height.
QUEUE_MAX_HEIGHT = 100


class _SectionHeader(QLabel):
    """Section title whose help text lives in a tooltip instead of a paragraph."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setTextFormat(Qt.TextFormat.PlainText)

    def set_texts(self, title: str, hint: str) -> None:
        self.setText(f"{title}  ⓘ")
        self.setToolTip(hint)


class InventoryFilterDialog(QDialog):
    """Popup filter form. Emits ``filters_changed`` on any edit."""

    filters_changed = Signal()

    def __init__(self, translator: Translator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._translator = translator
        self._cmc_rows: list[tuple[QComboBox, QSpinBox, QPushButton]] = []
        self._selected_subtypes: list[str] = []
        self._selected_decks: list[tuple[int, str]] = []
        self._armed_decks: list[tuple[int, str]] = []
        self._headers: list[tuple[_SectionHeader, str, str]] = []
        self.setModal(False)
        self.setMinimumWidth(420)
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        # Without this the scroll area advertises a fixed default height and the
        # dialog would scroll even when the form fits.
        self._scroll.setSizeAdjustPolicy(
            QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents
        )
        content = QWidget()
        body = QVBoxLayout(content)
        body.setContentsMargins(0, 0, 0, 0)
        self._scroll.setWidget(content)
        outer.addWidget(self._scroll, 1)

        # --- Availability ---
        body.addWidget(
            self._section_header(
                "inventory.filters.availability",
                "inventory.filters.availability_hint",
            )
        )
        self._only_free = QCheckBox()
        self._only_free.toggled.connect(self._on_filters_edited)
        body.addWidget(self._only_free)

        # --- Type (fixed list → checkboxes) ---
        body.addWidget(
            self._section_header(
                "inventory.filters.type", "inventory.filters.type_hint"
            )
        )
        types_grid = QGridLayout()
        self._type_checks: dict[str, QCheckBox] = {}
        for position, type_name in enumerate(CARD_TYPE_OPTIONS):
            box = QCheckBox(type_name)
            box.toggled.connect(self._on_filters_edited)
            self._type_checks[type_name] = box
            types_grid.addWidget(
                box, position // TYPE_COLUMNS, position % TYPE_COLUMNS
            )
        body.addLayout(types_grid)

        # --- Subtype (open-ended → searchable picker) ---
        body.addWidget(
            self._section_header(
                "inventory.filters.subtypes", "inventory.filters.subtypes_hint"
            )
        )
        subtype_picker = QHBoxLayout()
        self._subtype_combo = QComboBox()
        self._configure_searchable_combo(self._subtype_combo)
        self._subtype_add_button = QPushButton()
        self._subtype_add_button.clicked.connect(self._add_selected_subtype)
        subtype_picker.addWidget(self._subtype_combo, 1)
        subtype_picker.addWidget(self._subtype_add_button)
        body.addLayout(subtype_picker)

        self._subtype_queue_group = QGroupBox()
        subtype_queue_layout = QVBoxLayout(self._subtype_queue_group)
        self._subtype_queue = QListWidget()
        self._subtype_queue.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._subtype_queue.itemDoubleClicked.connect(self._remove_subtype_item)
        subtype_queue_layout.addWidget(self._subtype_queue)
        self._subtype_remove_button = QPushButton()
        self._subtype_remove_button.clicked.connect(self._remove_selected_subtype)
        subtype_queue_layout.addWidget(self._subtype_remove_button)
        body.addWidget(self._subtype_queue_group)
        self._subtype_queue_group.setVisible(False)

        # --- Decks ---
        body.addWidget(
            self._section_header(
                "inventory.filters.decks", "inventory.filters.decks_hint"
            )
        )
        self._exclude_any_armed = QCheckBox()
        self._exclude_any_armed.toggled.connect(self._on_filters_edited)
        body.addWidget(self._exclude_any_armed)

        deck_picker = QHBoxLayout()
        self._deck_combo = QComboBox()
        self._configure_searchable_combo(self._deck_combo)
        self._deck_add_button = QPushButton()
        self._deck_add_button.clicked.connect(self._add_selected_deck)
        deck_picker.addWidget(self._deck_combo, 1)
        deck_picker.addWidget(self._deck_add_button)
        body.addLayout(deck_picker)

        self._deck_queue_group = QGroupBox()
        deck_queue_layout = QVBoxLayout(self._deck_queue_group)
        self._deck_queue = QListWidget()
        self._deck_queue.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._deck_queue.itemDoubleClicked.connect(self._remove_deck_item)
        deck_queue_layout.addWidget(self._deck_queue)
        self._deck_remove_button = QPushButton()
        self._deck_remove_button.clicked.connect(self._remove_selected_deck)
        deck_queue_layout.addWidget(self._deck_remove_button)
        body.addWidget(self._deck_queue_group)
        self._deck_queue_group.setVisible(False)

        # --- Colors ---
        body.addWidget(
            self._section_header(
                "inventory.filters.colors", "inventory.filters.colors_hint"
            )
        )
        colors_row = QHBoxLayout()
        self._color_checks: dict[str, QCheckBox] = {}
        for letter in WUBRG:
            box = QCheckBox(letter)
            box.toggled.connect(self._on_filters_edited)
            self._color_checks[letter] = box
            colors_row.addWidget(box)
        colors_row.addStretch()
        body.addLayout(colors_row)

        # --- Rarity (same letter-checkbox style as colors) ---
        body.addWidget(
            self._section_header(
                "inventory.filters.rarity", "inventory.filters.rarity_hint"
            )
        )
        rarity_row = QHBoxLayout()
        self._rarity_checks: dict[str, QCheckBox] = {}
        for code in RARITY_CODES:
            box = QCheckBox(code)
            box.toggled.connect(self._on_filters_edited)
            self._rarity_checks[code] = box
            rarity_row.addWidget(box)
        rarity_row.addStretch()
        body.addLayout(rarity_row)

        # --- Mana value ---
        body.addWidget(
            self._section_header(
                "inventory.filters.cmc", "inventory.filters.cmc_hint"
            )
        )
        self._cmc_list_layout = QVBoxLayout()
        body.addLayout(self._cmc_list_layout)

        cmc_add_row = QHBoxLayout()
        self._cmc_op = QComboBox()
        configure_data_combo(self._cmc_op, min_contents=4)
        for op in CMC_OPS:
            self._cmc_op.addItem(op)
        self._cmc_value = QSpinBox()
        self._cmc_value.setRange(0, 99)
        self._cmc_value.setValue(1)
        self._cmc_add_button = QPushButton()
        self._cmc_add_button.clicked.connect(self._add_cmc_condition)
        cmc_add_row.addWidget(self._cmc_op)
        cmc_add_row.addWidget(self._cmc_value, 1)
        cmc_add_row.addWidget(self._cmc_add_button)
        body.addLayout(cmc_add_row)
        body.addStretch()

        footer = QHBoxLayout()
        self._clear_button = QPushButton()
        self._clear_button.clicked.connect(self.clear_filters)
        footer.addWidget(self._clear_button)
        footer.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        self._close_button = buttons.button(QDialogButtonBox.StandardButton.Close)
        footer.addWidget(buttons)
        outer.addLayout(footer)

        self.retranslate()

    def _section_header(self, title_key: str, hint_key: str) -> _SectionHeader:
        header = _SectionHeader()
        self._headers.append((header, title_key, hint_key))
        return header

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 (Qt naming)
        super().showEvent(event)
        self._cap_height_to_screen()

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt naming)
        """Open at the form's natural height; scroll only past the screen cap.

        `QScrollArea` caps its own hint at 24 text lines, which would make the
        dialog scroll even when everything fits.
        """
        hint = super().sizeHint()
        content = self._scroll.widget()
        if content is not None:
            overhead = hint.height() - self._scroll.sizeHint().height()
            hint.setHeight(content.sizeHint().height() + overhead)
        cap = self._screen_height_cap()
        if cap:
            hint.setHeight(min(hint.height(), cap))
        return hint

    def _screen_height_cap(self) -> int:
        screen = self.screen()
        if screen is None:
            return 0
        return int(screen.availableGeometry().height() * MAX_HEIGHT_RATIO)

    def _cap_height_to_screen(self) -> None:
        """Keep the dialog on screen; the scroll area absorbs the overflow."""
        cap = self._screen_height_cap()
        if cap:
            self.setMaximumHeight(cap)

    def _configure_searchable_combo(self, combo: QComboBox) -> None:
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        configure_data_combo(
            combo, min_contents=SEARCHABLE_COMBO_CONTENTS_LENGTH
        )
        line_edit = combo.lineEdit()
        assert line_edit is not None
        line_edit.setClearButtonEnabled(True)
        search_icon = self.style().standardIcon(
            QStyle.StandardPixmap.SP_FileDialogContentsView
        )
        search_action = QAction(
            search_icon if not search_icon.isNull() else QIcon(),
            "",
            self,
        )
        search_action.setEnabled(False)
        line_edit.addAction(search_action, line_edit.ActionPosition.LeadingPosition)
        completer = QCompleter(combo.model(), combo)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        combo.setCompleter(completer)
        combo.activated.connect(lambda *_: self._commit_combo(combo))
        line_edit.returnPressed.connect(lambda: self._commit_combo(combo))

    def retranslate(self) -> None:
        t = self._translator.t
        self.setWindowTitle(t("inventory.filters.title"))
        for header, title_key, hint_key in self._headers:
            header.set_texts(t(title_key), t(hint_key))

        self._only_free.setText(t("inventory.filters.only_free"))

        subtype_edit = self._subtype_combo.lineEdit()
        if subtype_edit is not None:
            subtype_edit.setPlaceholderText(t("inventory.filters.subtypes_search"))
        self._subtype_add_button.setText(t("inventory.filters.subtypes_add"))
        self._subtype_remove_button.setText(t("inventory.filters.subtypes_remove"))
        self._subtype_queue_group.setTitle(t("inventory.filters.subtypes_selected"))

        self._exclude_any_armed.setText(t("inventory.filters.decks_any_armed"))
        deck_edit = self._deck_combo.lineEdit()
        if deck_edit is not None:
            deck_edit.setPlaceholderText(t("inventory.filters.decks_search"))
        self._deck_add_button.setText(t("inventory.filters.decks_add"))
        self._deck_remove_button.setText(t("inventory.filters.decks_remove"))
        self._deck_queue_group.setTitle(t("inventory.filters.decks_selected"))

        for letter, box in self._color_checks.items():
            box.setToolTip(t(f"inventory.filters.color.{letter}"))
        for code, box in self._rarity_checks.items():
            box.setToolTip(t(f"inventory.filters.rarity.{code}"))
        self._cmc_add_button.setText(t("inventory.filters.cmc_add"))
        self._clear_button.setText(t("inventory.filters.clear"))
        if self._close_button is not None:
            self._close_button.setText(t("inventory.filters.close"))
        for _op, _spin, remove in self._cmc_rows:
            remove.setText(t("inventory.filters.cmc_remove"))

    def set_subtypes(self, subtypes: tuple[str, ...]) -> None:
        """Refresh the subtype picker with the subtypes present in the collection."""
        current = self._subtype_combo.currentText()
        self._subtype_combo.blockSignals(True)
        self._subtype_combo.clear()
        for subtype in subtypes:
            self._subtype_combo.addItem(subtype, subtype)
        completer = self._subtype_combo.completer()
        if completer is not None:
            completer.setModel(self._subtype_combo.model())
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._subtype_combo.setCurrentIndex(-1)
        line_edit = self._subtype_combo.lineEdit()
        if line_edit is not None:
            line_edit.setText(current)
        self._subtype_combo.blockSignals(False)

    def set_armed_decks(self, decks: list[tuple[int, str]]) -> None:
        """Refresh the armed-deck picker; drop queue entries that are no longer armed."""
        self._armed_decks = list(decks)
        valid_ids = {deck_id for deck_id, _name in self._armed_decks}

        kept = [(deck_id, name) for deck_id, name in self._selected_decks if deck_id in valid_ids]
        dropped = len(kept) != len(self._selected_decks)
        self._selected_decks = kept
        self._rebuild_deck_queue()

        current = self._deck_combo.currentData()
        self._deck_combo.blockSignals(True)
        self._deck_combo.clear()
        for deck_id, name in self._armed_decks:
            self._deck_combo.addItem(name, deck_id)
        completer = self._deck_combo.completer()
        if completer is not None:
            completer.setModel(self._deck_combo.model())
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            completer.setFilterMode(Qt.MatchFlag.MatchContains)
        if isinstance(current, int):
            index = self._deck_combo.findData(current)
            if index >= 0:
                self._deck_combo.setCurrentIndex(index)
            else:
                self._deck_combo.setCurrentIndex(-1)
                line_edit = self._deck_combo.lineEdit()
                if line_edit is not None:
                    line_edit.clear()
        else:
            self._deck_combo.setCurrentIndex(-1)
        self._deck_combo.blockSignals(False)

        if dropped:
            self.filters_changed.emit()

    def filter_state(self) -> InventoryFilterState:
        types = {
            name for name, box in self._type_checks.items() if box.isChecked()
        }
        colors = {
            letter
            for letter, box in self._color_checks.items()
            if box.isChecked()
        }
        rarities = {
            code for code, box in self._rarity_checks.items() if box.isChecked()
        }
        conditions = tuple(
            CmcCondition(op.currentText(), float(spin.value()))
            for op, spin, _remove in self._cmc_rows
        )
        return InventoryFilterState(
            types=frozenset(types),
            subtypes=frozenset(self._selected_subtypes),
            colors=frozenset(colors),
            rarities=frozenset(rarities),
            cmc_conditions=conditions,
            exclude_any_armed=self._exclude_any_armed.isChecked(),
            exclude_deck_ids=frozenset(deck_id for deck_id, _ in self._selected_decks),
            only_with_free=self._only_free.isChecked(),
        )

    def clear_filters(self) -> None:
        self._selected_subtypes.clear()
        self._rebuild_subtype_queue()
        self._selected_decks.clear()
        self._rebuild_deck_queue()
        for box in (
            self._only_free,
            self._exclude_any_armed,
            *self._type_checks.values(),
            *self._color_checks.values(),
            *self._rarity_checks.values(),
        ):
            box.blockSignals(True)
            box.setChecked(False)
            box.blockSignals(False)
        subtype_edit = self._subtype_combo.lineEdit()
        if subtype_edit is not None:
            subtype_edit.clear()
        self._subtype_combo.setCurrentIndex(-1)
        deck_edit = self._deck_combo.lineEdit()
        if deck_edit is not None:
            deck_edit.clear()
        self._deck_combo.setCurrentIndex(-1)
        while self._cmc_rows:
            self._remove_cmc_row(self._cmc_rows[0][2])
        self.filters_changed.emit()

    def _commit_combo(self, combo: QComboBox) -> None:
        data = self._combo_selection_data(combo)
        if data is None:
            return
        index = combo.findData(data)
        if index < 0:
            return
        combo.blockSignals(True)
        combo.setCurrentIndex(index)
        combo.blockSignals(False)

    def _combo_selection_data(self, combo: QComboBox) -> object | None:
        typed = combo.currentText().strip()
        if not typed:
            return None
        index = combo.currentIndex()
        if index >= 0 and combo.itemText(index) == typed:
            return combo.itemData(index)
        needle = typed.casefold()
        exact: list[object] = []
        partial: list[object] = []
        for i in range(combo.count()):
            label = combo.itemText(i)
            data = combo.itemData(i)
            if label.casefold() == needle:
                exact.append(data)
            elif needle in label.casefold():
                partial.append(data)
        if len(exact) == 1:
            return exact[0]
        if not exact and len(partial) == 1:
            return partial[0]
        return None

    def _add_selected_subtype(self) -> None:
        data = self._combo_selection_data(self._subtype_combo)
        if not isinstance(data, str):
            return
        if data in self._selected_subtypes:
            return
        self._selected_subtypes.append(data)
        self._rebuild_subtype_queue()
        line_edit = self._subtype_combo.lineEdit()
        if line_edit is not None:
            line_edit.clear()
        self._subtype_combo.setCurrentIndex(-1)
        self.filters_changed.emit()

    def _remove_subtype_item(self, item: QListWidgetItem) -> None:
        self._remove_subtype(item.text())

    def _remove_selected_subtype(self) -> None:
        item = self._subtype_queue.currentItem()
        if item is not None:
            self._remove_subtype(item.text())

    def _remove_subtype(self, subtype: str) -> None:
        if subtype not in self._selected_subtypes:
            return
        self._selected_subtypes = [
            name for name in self._selected_subtypes if name != subtype
        ]
        self._rebuild_subtype_queue()
        self.filters_changed.emit()

    def _rebuild_subtype_queue(self) -> None:
        self._subtype_queue.clear()
        for subtype in self._selected_subtypes:
            self._subtype_queue.addItem(subtype)
        self._fit_queue_height(self._subtype_queue)
        self._subtype_queue_group.setVisible(bool(self._selected_subtypes))

    def _add_selected_deck(self) -> None:
        data = self._combo_selection_data(self._deck_combo)
        if not isinstance(data, int):
            return
        if any(deck_id == data for deck_id, _ in self._selected_decks):
            return
        name = next(
            (n for deck_id, n in self._armed_decks if deck_id == data),
            self._deck_combo.currentText().strip(),
        )
        self._selected_decks.append((data, name))
        self._rebuild_deck_queue()
        line_edit = self._deck_combo.lineEdit()
        if line_edit is not None:
            line_edit.clear()
        self._deck_combo.setCurrentIndex(-1)
        self.filters_changed.emit()

    def _remove_deck_item(self, item: QListWidgetItem) -> None:
        deck_id = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(deck_id, int):
            self._remove_deck(deck_id)

    def _remove_selected_deck(self) -> None:
        item = self._deck_queue.currentItem()
        if item is None:
            return
        deck_id = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(deck_id, int):
            self._remove_deck(deck_id)

    def _remove_deck(self, deck_id: int) -> None:
        before = len(self._selected_decks)
        self._selected_decks = [
            (did, name) for did, name in self._selected_decks if did != deck_id
        ]
        if len(self._selected_decks) == before:
            return
        self._rebuild_deck_queue()
        self.filters_changed.emit()

    def _rebuild_deck_queue(self) -> None:
        self._deck_queue.clear()
        for deck_id, name in self._selected_decks:
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, deck_id)
            self._deck_queue.addItem(item)
        self._fit_queue_height(self._deck_queue)
        self._deck_queue_group.setVisible(bool(self._selected_decks))

    def _fit_queue_height(self, queue: QListWidget) -> None:
        """Grow the list with its items instead of reserving a fixed box."""
        rows = max(1, queue.count())
        row_height = (
            queue.sizeHintForRow(0)
            if queue.count()
            else queue.fontMetrics().height() + 4
        )
        queue.setFixedHeight(
            min(QUEUE_MAX_HEIGHT, rows * row_height + 2 * queue.frameWidth())
        )

    def _add_cmc_condition(self) -> None:
        op = QComboBox()
        configure_data_combo(op, min_contents=4)
        for symbol in CMC_OPS:
            op.addItem(symbol)
        op.setCurrentText(self._cmc_op.currentText())
        op.currentIndexChanged.connect(self._on_filters_edited)

        spin = QSpinBox()
        spin.setRange(0, 99)
        spin.setValue(self._cmc_value.value())
        spin.valueChanged.connect(self._on_filters_edited)

        remove = QPushButton(self._translator.t("inventory.filters.cmc_remove"))
        row_widget = QWidget()
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(op)
        row.addWidget(spin, 1)
        row.addWidget(remove)
        remove.clicked.connect(lambda: self._remove_cmc_row(remove))

        self._cmc_list_layout.addWidget(row_widget)
        self._cmc_rows.append((op, spin, remove))
        self.filters_changed.emit()

    def _remove_cmc_row(self, remove_button: QPushButton) -> None:
        for index, (op, spin, button) in enumerate(self._cmc_rows):
            if button is not remove_button:
                continue
            widget = button.parentWidget()
            self._cmc_rows.pop(index)
            if widget is not None:
                self._cmc_list_layout.removeWidget(widget)
                widget.deleteLater()
            self.filters_changed.emit()
            return

    def _on_filters_edited(self, *_args: object) -> None:
        self.filters_changed.emit()
