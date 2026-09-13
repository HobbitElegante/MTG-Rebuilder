"""Inventory filter dialog (availability / type / subtype / decks / colors / rarity / mana value)."""

from __future__ import annotations

from collections.abc import Callable, Iterable

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
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from mtg_rebuilder.algorithms.inventory_filters import (
    CARD_TYPE_OPTIONS,
    CMC_OPS,
    COLOR_MODES,
    RARITY_CODES,
    CmcCondition,
    ColorMode,
    FilterChip,
    FilterChipKind,
    InventoryFilterState,
    WUBRG,
    cmc_conditions_issue,
    resolve_cmc_add,
)
from mtg_rebuilder.i18n import Translator
from mtg_rebuilder.ui.combo import (
    SEARCHABLE_COMBO_CONTENTS_LENGTH,
    configure_data_combo,
)
from mtg_rebuilder.ui.filter_picker import (
    PickerResolution,
    format_picker_hint,
    resolve_picker_text,
)
from mtg_rebuilder.ui.inventory_display import format_cmc_hint
from mtg_rebuilder.ui.mana_icons import symbol_icon
from mtg_rebuilder.ui.widgets.chip_bar import Chip, ChipBar

# Type checkboxes per row; 3 keeps the longest label ("Planeswalker") readable
# at the dialog's minimum width.
TYPE_COLUMNS = 3
# Share of the screen the dialog may take before its content starts scrolling.
MAX_HEIGHT_RATIO = 0.85


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
        self._configure_searchable_combo(
            self._subtype_combo, self._add_selected_subtype
        )
        self._subtype_add_button = QPushButton()
        self._subtype_add_button.clicked.connect(self._add_selected_subtype)
        subtype_picker.addWidget(self._subtype_combo, 1)
        subtype_picker.addWidget(self._subtype_add_button)
        body.addLayout(subtype_picker)
        self._subtype_hint = self._picker_hint()
        body.addWidget(self._subtype_hint)

        self._subtype_queue_group = QGroupBox()
        subtype_queue_layout = QVBoxLayout(self._subtype_queue_group)
        self._subtype_chips = ChipBar()
        self._subtype_chips.chip_removed.connect(self._on_subtype_chip_removed)
        subtype_queue_layout.addWidget(self._subtype_chips)
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
        self._configure_searchable_combo(self._deck_combo, self._add_selected_deck)
        self._deck_add_button = QPushButton()
        self._deck_add_button.clicked.connect(self._add_selected_deck)
        deck_picker.addWidget(self._deck_combo, 1)
        deck_picker.addWidget(self._deck_add_button)
        body.addLayout(deck_picker)
        self._deck_hint = self._picker_hint()
        body.addWidget(self._deck_hint)

        self._deck_queue_group = QGroupBox()
        deck_queue_layout = QVBoxLayout(self._deck_queue_group)
        self._deck_chips = ChipBar()
        self._deck_chips.chip_removed.connect(self._on_deck_chip_removed)
        deck_queue_layout.addWidget(self._deck_chips)
        body.addWidget(self._deck_queue_group)
        self._deck_queue_group.setVisible(False)

        # --- Colors ---
        body.addWidget(
            self._section_header(
                "inventory.filters.colors", "inventory.filters.colors_hint"
            )
        )
        color_mode_row = QHBoxLayout()
        self._color_mode_label = QLabel()
        self._color_mode_combo = QComboBox()
        configure_data_combo(self._color_mode_combo, min_contents=16)
        for mode in COLOR_MODES:
            self._color_mode_combo.addItem("", mode.value)
        self._color_mode_combo.currentIndexChanged.connect(self._on_filters_edited)
        color_mode_row.addWidget(self._color_mode_label)
        color_mode_row.addWidget(self._color_mode_combo, 1)
        body.addLayout(color_mode_row)

        colors_row = QHBoxLayout()
        self._color_checks: dict[str, QCheckBox] = {}
        for letter in WUBRG:
            box = QCheckBox()
            box.setIcon(symbol_icon(letter, size=16))
            box.toggled.connect(self._on_filters_edited)
            self._color_checks[letter] = box
            colors_row.addWidget(box)
        colors_row.addStretch()
        body.addLayout(colors_row)

        # Zero checkboxes means "no filter", so the empty identity needs its own
        # switch; it overrides the mode and the letters.
        self._only_colorless = QCheckBox()
        self._only_colorless.toggled.connect(self._on_colorless_toggled)
        body.addWidget(self._only_colorless)

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
        self._cmc_op.currentIndexChanged.connect(self._sync_cmc)
        self._cmc_value = QSpinBox()
        self._cmc_value.setRange(0, 99)
        self._cmc_value.setValue(1)
        self._cmc_value.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed
        )
        self._cmc_value.valueChanged.connect(self._sync_cmc)
        self._cmc_add_button = QPushButton()
        self._cmc_add_button.clicked.connect(self._add_cmc_condition)
        # Operator stretches; the number stays compact (was the other way around).
        cmc_add_row.addWidget(self._cmc_op, 1)
        cmc_add_row.addWidget(self._cmc_value)
        cmc_add_row.addWidget(self._cmc_add_button)
        body.addLayout(cmc_add_row)
        self._cmc_hint = self._picker_hint()
        body.addWidget(self._cmc_hint)
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

        self._sync_color_controls()
        self.retranslate()

    def _section_header(self, title_key: str, hint_key: str) -> _SectionHeader:
        header = _SectionHeader()
        self._headers.append((header, title_key, hint_key))
        return header

    def _picker_hint(self) -> QLabel:
        """Small line that says why *Add* is disabled; hidden when it is not."""
        label = QLabel()
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.PlainText)
        font = label.font()
        font.setPointSize(max(8, font.pointSize() - 1))
        label.setFont(font)
        label.setVisible(False)
        return label

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 (Qt naming)
        super().showEvent(event)
        self._cap_height_to_screen()
        self._fit_height_to_content()

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

    def _fit_height_to_content(self) -> None:
        """Bypass Qt's first-show 2/3-screen adjustSize so an empty form has no scroll.

        ``show()`` calls ``adjustSize()``, which caps top-level widgets at two
        thirds of the screen. Our form is taller than that on typical displays
        but still under the 85% cap in ``sizeHint``, so the default open left a
        short scrollbar for no reason. Apply the hint ourselves every show.
        """
        hint = self.sizeHint()
        self.resize(
            max(self.width(), hint.width(), self.minimumWidth()),
            hint.height(),
        )

    def _configure_searchable_combo(
        self, combo: QComboBox, on_commit: Callable[[], None]
    ) -> None:
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
        # Enter (or picking from the popup) adds straight away when the text
        # resolves; otherwise the hint below the picker explains why it did not.
        line_edit.returnPressed.connect(on_commit)
        combo.activated.connect(lambda *_: on_commit())
        combo.editTextChanged.connect(lambda *_: self._sync_pickers())
        combo.currentIndexChanged.connect(lambda *_: self._sync_pickers())

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
        self._subtype_queue_group.setTitle(t("inventory.filters.subtypes_selected"))
        self._subtype_chips.set_texts(
            remove_tooltip=t("inventory.filters.chip_remove_tip")
        )

        self._exclude_any_armed.setText(t("inventory.filters.decks_any_armed"))
        deck_edit = self._deck_combo.lineEdit()
        if deck_edit is not None:
            deck_edit.setPlaceholderText(t("inventory.filters.decks_search"))
        self._deck_add_button.setText(t("inventory.filters.decks_add"))
        self._deck_queue_group.setTitle(t("inventory.filters.decks_selected"))
        self._deck_chips.set_texts(
            remove_tooltip=t("inventory.filters.chip_remove_tip")
        )

        self._color_mode_label.setText(t("inventory.filters.colors_mode"))
        for index, mode in enumerate(COLOR_MODES):
            self._color_mode_combo.setItemText(
                index, t(f"inventory.filters.colors_mode.{mode.value}")
            )
        self._only_colorless.setText(t("inventory.filters.colors_colorless"))
        for letter, box in self._color_checks.items():
            tip = t(f"inventory.filters.color.{letter}")
            box.setToolTip(tip)
            box.setAccessibleName(tip)
        for code, box in self._rarity_checks.items():
            box.setToolTip(t(f"inventory.filters.rarity.{code}"))
        self._cmc_add_button.setText(t("inventory.filters.cmc_add"))
        self._clear_button.setText(t("inventory.filters.clear"))
        if self._close_button is not None:
            self._close_button.setText(t("inventory.filters.close"))
        for _op, _spin, remove in self._cmc_rows:
            remove.setText(t("inventory.filters.cmc_remove"))
        self._sync_pickers()
        self._sync_cmc()

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
        self._sync_pickers()

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
        self._sync_pickers()

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
            color_mode=self._current_color_mode(),
            only_colorless=self._only_colorless.isChecked(),
            rarities=frozenset(rarities),
            cmc_conditions=conditions,
            exclude_any_armed=self._exclude_any_armed.isChecked(),
            exclude_deck_ids=frozenset(deck_id for deck_id, _ in self._selected_decks),
            only_with_free=self._only_free.isChecked(),
        )

    def selected_deck_names(self) -> dict[int, str]:
        """Deck id → name for the excluded decks, so chips can be labelled."""
        return {deck_id: name for deck_id, name in self._selected_decks}

    def clear_filters(self) -> None:
        self._selected_subtypes.clear()
        self._rebuild_subtype_queue()
        self._selected_decks.clear()
        self._rebuild_deck_queue()
        for box in (
            self._only_free,
            self._exclude_any_armed,
            self._only_colorless,
            *self._type_checks.values(),
            *self._color_checks.values(),
            *self._rarity_checks.values(),
        ):
            box.blockSignals(True)
            box.setChecked(False)
            box.blockSignals(False)
        self._color_mode_combo.blockSignals(True)
        self._color_mode_combo.setCurrentIndex(0)
        self._color_mode_combo.blockSignals(False)
        self._sync_color_controls()
        self._clear_combo_text(self._subtype_combo)
        self._clear_combo_text(self._deck_combo)
        while self._cmc_rows:
            self._remove_cmc_row(self._cmc_rows[0][2], notify=False)
        self._sync_pickers()
        self._sync_cmc()
        self.filters_changed.emit()

    def remove_chip(self, chip: FilterChip) -> None:
        """Drop one active filter, as shown in the chip bar above the table."""
        if chip.kind is FilterChipKind.SUBTYPE:
            self._remove_subtype(chip.value)
            return
        if chip.kind is FilterChipKind.DECK:
            self._remove_deck(int(chip.value))
            return
        if chip.kind is FilterChipKind.CMC:
            index = int(chip.value)
            if 0 <= index < len(self._cmc_rows):
                self._remove_cmc_row(self._cmc_rows[index][2])
            return
        if chip.kind is FilterChipKind.TYPE:
            box = self._type_checks.get(chip.value)
            if box is not None:
                box.setChecked(False)
            return
        if chip.kind is FilterChipKind.ONLY_FREE:
            self._only_free.setChecked(False)
            return
        if chip.kind is FilterChipKind.ANY_ARMED:
            self._exclude_any_armed.setChecked(False)
            return
        if chip.kind is FilterChipKind.COLORLESS:
            self._only_colorless.setChecked(False)
            return
        if chip.kind is FilterChipKind.COLORS:
            self._uncheck_group(self._color_checks.values())
            return
        if chip.kind is FilterChipKind.RARITY:
            self._uncheck_group(self._rarity_checks.values())

    def _uncheck_group(self, boxes: Iterable[QCheckBox]) -> None:
        """Clear a whole checkbox group with a single ``filters_changed``."""
        changed = False
        for box in boxes:
            if not box.isChecked():
                continue
            box.blockSignals(True)
            box.setChecked(False)
            box.blockSignals(False)
            changed = True
        if changed:
            self.filters_changed.emit()

    def _current_color_mode(self) -> ColorMode:
        try:
            return ColorMode(self._color_mode_combo.currentData())
        except ValueError:
            return ColorMode.AT_MOST

    def _on_colorless_toggled(self, _checked: bool) -> None:
        self._sync_color_controls()
        self.filters_changed.emit()

    def _sync_color_controls(self) -> None:
        """"Only colorless" wins, so the mode and the letters go grey."""
        enabled = not self._only_colorless.isChecked()
        self._color_mode_label.setEnabled(enabled)
        self._color_mode_combo.setEnabled(enabled)
        for box in self._color_checks.values():
            box.setEnabled(enabled)

    def _clear_combo_text(self, combo: QComboBox) -> None:
        line_edit = combo.lineEdit()
        if line_edit is not None:
            line_edit.clear()
        combo.setCurrentIndex(-1)

    def _combo_options(self, combo: QComboBox) -> list[str]:
        return [combo.itemText(index) for index in range(combo.count())]

    def _resolve_subtype(self) -> PickerResolution:
        return resolve_picker_text(
            self._combo_options(self._subtype_combo),
            self._subtype_combo.currentText(),
            self._selected_subtypes,
        )

    def _resolve_deck(self) -> PickerResolution:
        return resolve_picker_text(
            self._combo_options(self._deck_combo),
            self._deck_combo.currentText(),
            [name for _deck_id, name in self._selected_decks],
        )

    def _sync_pickers(self) -> None:
        """Enable each *Add* only when its text resolves, and say why if not."""
        self._apply_picker_state(
            self._resolve_subtype(),
            self._subtype_combo,
            self._subtype_add_button,
            self._subtype_hint,
        )
        self._apply_picker_state(
            self._resolve_deck(),
            self._deck_combo,
            self._deck_add_button,
            self._deck_hint,
        )

    def _apply_picker_state(
        self,
        resolution: PickerResolution,
        combo: QComboBox,
        button: QPushButton,
        hint: QLabel,
    ) -> None:
        button.setEnabled(resolution.can_add)
        message = format_picker_hint(
            resolution, combo.currentText(), self._translator
        )
        hint.setText(message)
        hint.setVisible(bool(message))

    def _add_selected_subtype(self) -> None:
        resolution = self._resolve_subtype()
        if not resolution.can_add:
            self._sync_pickers()
            return
        self._selected_subtypes.append(resolution.label)
        self._rebuild_subtype_queue()
        self._clear_combo_text(self._subtype_combo)
        self._sync_pickers()
        self.filters_changed.emit()

    def _on_subtype_chip_removed(self, key: object) -> None:
        if isinstance(key, str):
            self._remove_subtype(key)

    def _remove_subtype(self, subtype: str) -> None:
        if subtype not in self._selected_subtypes:
            return
        self._selected_subtypes = [
            name for name in self._selected_subtypes if name != subtype
        ]
        self._rebuild_subtype_queue()
        self._sync_pickers()
        self.filters_changed.emit()

    def _rebuild_subtype_queue(self) -> None:
        self._subtype_chips.set_chips(
            [Chip(key=name, label=name) for name in self._selected_subtypes]
        )
        self._subtype_queue_group.setVisible(bool(self._selected_subtypes))

    def _add_selected_deck(self) -> None:
        resolution = self._resolve_deck()
        if not resolution.can_add:
            self._sync_pickers()
            return
        deck_id = self._deck_combo.itemData(resolution.index)
        if not isinstance(deck_id, int):
            return
        self._selected_decks.append((deck_id, resolution.label))
        self._rebuild_deck_queue()
        self._clear_combo_text(self._deck_combo)
        self._sync_pickers()
        self.filters_changed.emit()

    def _on_deck_chip_removed(self, key: object) -> None:
        if isinstance(key, int):
            self._remove_deck(key)

    def _remove_deck(self, deck_id: int) -> None:
        before = len(self._selected_decks)
        self._selected_decks = [
            (did, name) for did, name in self._selected_decks if did != deck_id
        ]
        if len(self._selected_decks) == before:
            return
        self._rebuild_deck_queue()
        self._sync_pickers()
        self.filters_changed.emit()

    def _rebuild_deck_queue(self) -> None:
        self._deck_chips.set_chips(
            [Chip(key=deck_id, label=name) for deck_id, name in self._selected_decks]
        )
        self._deck_queue_group.setVisible(bool(self._selected_decks))

    def _add_cmc_condition(self) -> None:
        resolution = resolve_cmc_add(
            self.filter_state().cmc_conditions,
            self._cmc_op.currentText(),
            float(self._cmc_value.value()),
        )
        if not resolution.can_add:
            self._sync_cmc()
            return

        op = QComboBox()
        configure_data_combo(op, min_contents=4)
        for symbol in CMC_OPS:
            op.addItem(symbol)
        op.setCurrentText(self._cmc_op.currentText())
        op.currentIndexChanged.connect(self._on_filters_edited)

        spin = QSpinBox()
        spin.setRange(0, 99)
        spin.setValue(self._cmc_value.value())
        spin.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed
        )
        spin.valueChanged.connect(self._on_filters_edited)

        remove = QPushButton(self._translator.t("inventory.filters.cmc_remove"))
        row_widget = QWidget()
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(op, 1)
        row.addWidget(spin)
        row.addWidget(remove)
        remove.clicked.connect(lambda: self._remove_cmc_row(remove))

        self._cmc_list_layout.addWidget(row_widget)
        self._cmc_rows.append((op, spin, remove))
        self._sync_cmc()
        self.filters_changed.emit()

    def _remove_cmc_row(
        self, remove_button: QPushButton, *, notify: bool = True
    ) -> None:
        for index, (_op, _spin, button) in enumerate(self._cmc_rows):
            if button is not remove_button:
                continue
            widget = button.parentWidget()
            self._cmc_rows.pop(index)
            if widget is not None:
                self._cmc_list_layout.removeWidget(widget)
                widget.deleteLater()
            if notify:
                self._sync_cmc()
                self.filters_changed.emit()
            return

    def _on_filters_edited(self, *_args: object) -> None:
        self._sync_cmc()
        self.filters_changed.emit()

    def _sync_cmc(self, *_args: object) -> None:
        """Enable CMC *Add* only when the draft row is useful; warn on bad sets."""
        existing = self.filter_state().cmc_conditions
        op = self._cmc_op.currentText()
        value = float(self._cmc_value.value())
        add = resolve_cmc_add(existing, op, value)
        self._cmc_add_button.setEnabled(add.can_add)
        message = format_cmc_hint(
            add, cmc_conditions_issue(existing), op, value, self._translator
        )
        self._cmc_hint.setText(message)
        self._cmc_hint.setVisible(bool(message))
