"""Widgets for recording print facts on physical copies."""

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
)

from mtg_rebuilder.algorithms.copy_traits import (
    CONDITION_VALUES,
    FINISH_VALUES,
    LANGUAGE_VALUES,
    CopyTraits,
    assign_printing,
    normalize_edition,
)
from mtg_rebuilder.ui.widgets.print_picker import PrintPickerDialog, format_print_label
from mtg_rebuilder.config import UNSPECIFIED_EDITION_LABEL
from mtg_rebuilder.database import get_session
from mtg_rebuilder.i18n import Translator
from mtg_rebuilder.services import ScryfallService
from mtg_rebuilder.ui.combo import (
    EDITION_COMBO_CONTENTS_LENGTH,
    configure_data_combo,
)


def normalize_edition_text(text: str) -> str | None:
    """Free-typed set codes are stored uppercase; blank means unspecified."""
    return normalize_edition(text)


class EditionComboBox(QComboBox):
    """Editable set-code picker that loads printings when first opened.

    The oracle cache has one row per card, so the list of sets is fetched from
    Scryfall the first time the user opens the popup and cached from then on.
    Offline it stays usable: the current value and free typing still work.
    """

    def __init__(
        self,
        oracle_id: str,
        current: str | None,
        translator: Translator,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._oracle_id = oracle_id
        self._translator = translator
        self._loaded = False
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        configure_data_combo(self, min_contents=EDITION_COMBO_CONTENTS_LENGTH)
        self._populate([], current)

    def _populate(self, prints: list[tuple[str, str | None]], current: str | None) -> None:
        self.blockSignals(True)
        self.clear()
        self.addItem(UNSPECIFIED_EDITION_LABEL, None)
        codes = {code for code, _ in prints}
        for code, set_name in prints:
            self.addItem(f"{code} — {set_name}" if set_name else code, code)
        if current and current not in codes:
            self.addItem(current, current)
        index = self.findData(current) if current else 0
        self.setCurrentIndex(index if index >= 0 else 0)
        self.blockSignals(False)

    def showPopup(self) -> None:
        if not self._loaded:
            self._loaded = True
            try:
                with get_session() as session:
                    service = ScryfallService(session)
                    try:
                        prints = service.list_prints(self._oracle_id)
                    finally:
                        service.close()
            except Exception:
                prints = []
            if prints:
                self._populate(prints, self.edition())
        super().showPopup()

    def edition(self) -> str | None:
        index = self.currentIndex()
        if index >= 0 and self.currentText() == self.itemText(index):
            data = self.itemData(index)
            return str(data) if data is not None else None
        return normalize_edition_text(self.currentText())

    def set_edition(self, edition: str | None) -> None:
        self.blockSignals(True)
        index = self.findData(edition) if edition else 0
        if index >= 0:
            self.setCurrentIndex(index)
        else:
            self.setEditText(edition or UNSPECIFIED_EDITION_LABEL)
        self.blockSignals(False)


class PrintingComboBox(QComboBox):
    """Art picker. Loads Scryfall printings the first time it opens.

    Offline, or before that, it offers unspecified plus the id already stored.
    The list is limited to the set currently chosen on the row when there is one.
    """

    def __init__(
        self,
        oracle_id: str,
        current: str | None,
        edition_getter: Callable[[], str | None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._oracle_id = oracle_id
        self._edition_getter = edition_getter
        self._loaded = False
        self._rows: list[tuple[str, str, str | None, str | None]] = []
        self.setEditable(False)
        configure_data_combo(self, min_contents=EDITION_COMBO_CONTENTS_LENGTH)
        self._show(current)

    def _show(self, current: str | None) -> None:
        edition = self._edition_getter() if self._loaded else None
        visible = self._rows
        if edition:
            visible = [row for row in self._rows if row[1] == edition]
        self.blockSignals(True)
        self.clear()
        self.addItem(UNSPECIFIED_EDITION_LABEL, None)
        seen: set[str] = set()
        for scryfall_id, _set_code, collector, label, _image in visible:
            text = label or collector or scryfall_id
            self.addItem(text, (scryfall_id, _set_code, collector))
            seen.add(scryfall_id)
        if current and current not in seen:
            self.addItem(current, (current, edition, None))
        self._select(current)
        self.blockSignals(False)

    def _select(self, current: str | None) -> None:
        if not current:
            self.setCurrentIndex(0)
            return
        for index in range(self.count()):
            data = self.itemData(index)
            if isinstance(data, tuple) and data[0] == current:
                self.setCurrentIndex(index)
                return
        self.setCurrentIndex(0)

    def showPopup(self) -> None:
        if not self._loaded:
            self._loaded = True
            current = self.printing_id()
            try:
                with get_session() as session:
                    service = ScryfallService(session)
                    try:
                        self._rows = service.list_printings(self._oracle_id)
                    finally:
                        service.close()
            except Exception:
                self._rows = []
            self._show(current)
        super().showPopup()

    def printing_id(self) -> str | None:
        data = self.currentData()
        if isinstance(data, tuple) and data[0]:
            return str(data[0])
        return None

    def choice(self) -> tuple[str, str | None, str | None] | None:
        """``(scryfall_id, set_code, collector_number)`` or None when unspecified."""
        data = self.currentData()
        if not isinstance(data, tuple) or not data[0]:
            return None
        scryfall_id, set_code, collector = data
        return (str(scryfall_id), str(set_code) if set_code else None, collector)

    def set_printing(self, printing_id: str | None) -> None:
        self.blockSignals(True)
        if printing_id and self.findData(printing_id) < 0:
            # findData does not match a tuple's first element.
            found = False
            for index in range(self.count()):
                data = self.itemData(index)
                if isinstance(data, tuple) and data[0] == printing_id:
                    found = True
                    break
            if not found:
                self.addItem(printing_id, (printing_id, None, None))
        self._select(printing_id)
        self.blockSignals(False)


def _choice_combo(
    options: list[tuple[str, str | None]],
    current: str | None,
) -> QComboBox:
    combo = QComboBox()
    configure_data_combo(combo, min_contents=8)
    combo.addItem(UNSPECIFIED_EDITION_LABEL, None)
    for label, value in options:
        combo.addItem(label, value)
    if current and combo.findData(current) < 0:
        combo.addItem(current, current)
    index = combo.findData(current) if current else 0
    combo.setCurrentIndex(index if index >= 0 else 0)
    return combo


def _combo_value(combo: QComboBox) -> str | None:
    data = combo.currentData()
    return str(data) if data is not None else None


def _set_combo_value(combo: QComboBox, value: str | None) -> None:
    combo.blockSignals(True)
    index = combo.findData(value) if value else 0
    combo.setCurrentIndex(index if index >= 0 else 0)
    combo.blockSignals(False)


class _CopyEditors:
    def __init__(
        self,
        finish: QComboBox,
        language: QComboBox,
        condition: QComboBox,
        print_button: QPushButton,
        *,
        edition: str | None,
        collector_number: str | None,
        printing_id: str | None,
    ) -> None:
        self.finish = finish
        self.language = language
        self.condition = condition
        self.print_button = print_button
        self.edition = edition
        self.collector_number = collector_number
        self.printing_id = printing_id

    def traits(self) -> CopyTraits:
        return CopyTraits(
            edition=self.edition,
            finish=_combo_value(self.finish),
            language=_combo_value(self.language),
            condition=_combo_value(self.condition),
            collector_number=self.collector_number,
            printing_id=self.printing_id,
        )

    def set_printing(
        self,
        edition: str | None,
        collector_number: str | None,
        printing_id: str | None,
    ) -> None:
        self.edition = edition
        self.collector_number = collector_number
        self.printing_id = printing_id
        self.print_button.setText(format_print_label(edition, collector_number))


def _language_combo(current: str | None) -> QComboBox:
    return _choice_combo(
        [(code.upper(), code) for code in LANGUAGE_VALUES],
        current,
    )


class CopyEditionTable(QTableWidget):
    """One row per copy: finish, language, condition, and a print grid."""

    def __init__(self, translator: Translator, parent=None) -> None:
        super().__init__(0, 5, parent)
        self._translator = translator
        self._oracle_ids: dict[int, str] = {}
        self._editors: dict[int, _CopyEditors] = {}
        self._apply_print: tuple[str | None, str | None, str | None] | None = None
        self.setHorizontalHeaderLabels(self._header_labels())
        header = self.horizontalHeader()
        for column in range(5):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(34)
        self.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.setMinimumHeight(160)

    def _header_labels(self) -> list[str]:
        return [
            self._translator.t("inventory.editions.copy"),
            self._translator.t("inventory.editions.finish"),
            self._translator.t("inventory.editions.language"),
            self._translator.t("inventory.editions.condition"),
            self._translator.t("inventory.prints.column"),
        ]

    def set_copies(
        self,
        copies: list[tuple[int, str, str, CopyTraits]],
    ) -> None:
        """``copies`` holds ``(copy_id, oracle_id, label, traits)``."""
        self._editors.clear()
        self._oracle_ids.clear()
        self.setRowCount(len(copies))
        for index, (copy_id, oracle_id, label, traits) in enumerate(copies):
            item = QTableWidgetItem(label)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.setItem(index, 0, item)
            finish = _choice_combo(
                [
                    (self._translator.t(f"inventory.finish.{name}"), name)
                    for name in FINISH_VALUES
                ],
                traits.finish,
            )
            language = _language_combo(traits.language)
            condition = _choice_combo(
                [(code, code) for code in CONDITION_VALUES],
                traits.condition,
            )
            print_button = QPushButton(
                format_print_label(traits.edition, traits.collector_number)
            )
            print_button.clicked.connect(
                lambda _checked=False, cid=copy_id: self._pick_print(cid)
            )
            editors = _CopyEditors(
                finish,
                language,
                condition,
                print_button,
                edition=traits.edition,
                collector_number=traits.collector_number,
                printing_id=traits.printing_id,
            )
            self._oracle_ids[copy_id] = oracle_id
            self._editors[copy_id] = editors
            self.setCellWidget(index, 1, finish)
            self.setCellWidget(index, 2, language)
            self.setCellWidget(index, 3, condition)
            self.setCellWidget(index, 4, print_button)

    def _pick_print(self, copy_id: int) -> None:
        editors = self._editors.get(copy_id)
        oracle_id = self._oracle_ids.get(copy_id)
        if editors is None or oracle_id is None:
            return
        dialog = PrintPickerDialog(
            self._translator,
            oracle_id,
            editors.printing_id,
            self,
            current_set=editors.edition,
            current_collector=editors.collector_number,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        printing_id, set_code, collector = dialog.printing()
        edition, number, chosen_id = assign_printing(
            chosen_id=printing_id,
            chosen_set=set_code,
            chosen_collector=collector,
        )
        editors.set_printing(edition, number, chosen_id)

    def traits(self) -> dict[int, CopyTraits]:
        return {copy_id: editors.traits() for copy_id, editors in self._editors.items()}

    def populate_apply_row(self, layout: QHBoxLayout, oracle_id: str) -> None:
        """Apply finish, language, and condition when they are not ``-``.

        The print button opens the same grid. Choosing a picture, clearing it,
        or typing a set and number there is applied to every copy of this card.
        Leaving that button untouched does not change the printings.
        """
        blank = CopyTraits()
        self._apply_oracle_id = oracle_id
        self._apply_print = None
        self._apply_finish = _choice_combo(
            [
                (self._translator.t(f"inventory.finish.{name}"), name)
                for name in FINISH_VALUES
            ],
            blank.finish,
        )
        self._apply_language = _language_combo(blank.language)
        self._apply_condition = _choice_combo(
            [(code, code) for code in CONDITION_VALUES],
            blank.condition,
        )
        self._apply_print_button = QPushButton(
            self._translator.t("inventory.prints.column")
        )
        self._apply_print_button.clicked.connect(self._pick_apply_print)
        apply = QPushButton(self._translator.t("inventory.editions.apply_all"))
        apply.clicked.connect(self._apply_bar)
        for widget in (
            self._apply_finish,
            self._apply_language,
            self._apply_condition,
            self._apply_print_button,
        ):
            layout.addWidget(widget, 1)
        layout.addWidget(apply)

    def _pick_apply_print(self) -> None:
        current_id, current_set, current_collector = self._apply_print or (
            None,
            None,
            None,
        )
        dialog = PrintPickerDialog(
            self._translator,
            self._apply_oracle_id,
            current_id,
            self,
            current_set=current_set,
            current_collector=current_collector,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        printing_id, set_code, collector = dialog.printing()
        self._apply_print = assign_printing(
            chosen_id=printing_id,
            chosen_set=set_code,
            chosen_collector=collector,
        )
        edition, number, _printing = self._apply_print
        self._apply_print_button.setText(format_print_label(edition, number))

    def _apply_bar(self) -> None:
        finish = _combo_value(self._apply_finish)
        language = _combo_value(self._apply_language)
        condition = _combo_value(self._apply_condition)
        for editors in self._editors.values():
            if finish is not None:
                _set_combo_value(editors.finish, finish)
            if language is not None:
                _set_combo_value(editors.language, language)
            if condition is not None:
                _set_combo_value(editors.condition, condition)
            if self._apply_print is not None:
                edition, number, printing_id = self._apply_print
                editors.set_printing(edition, number, printing_id)

    def retranslate(self) -> None:
        self.setHorizontalHeaderLabels(self._header_labels())
