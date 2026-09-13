from pathlib import Path

from PySide6.QtCore import QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QIcon, QShowEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from mtg_rebuilder.algorithms.inventory_filters import (
    FilterChip,
    filter_inventory_cards,
    subtype_catalog,
)
from mtg_rebuilder.api.scryfall_client import ScryfallClient
from mtg_rebuilder.database import get_session
from mtg_rebuilder.i18n import Translator
from mtg_rebuilder.models.enums import DeckStatus
from mtg_rebuilder.services import (
    BrowseService,
    ImportService,
    InventoryService,
    ScryfallService,
    SettingsService,
)
from mtg_rebuilder.services.browse_service import CardSummary, InventorySummaryRow
from mtg_rebuilder.services.deck_service import CopyDetail, DeckService
from mtg_rebuilder.ui.combo import configure_data_combo
from mtg_rebuilder.ui.error_text import format_deck_url_error
from mtg_rebuilder.ui.inventory_display import (
    format_color_identity,
    format_edition_summary,
    format_filter_button_label,
    format_filter_chips,
    format_inventory_decks,
    format_mana_value,
    format_rarity_summary,
    rarity_sort_rank,
)
from mtg_rebuilder.ui.mana_icons import color_identity_pixmap
from mtg_rebuilder.ui.scryfall_icon import scryfall_icon
from mtg_rebuilder.ui.widgets.card_preview import (
    CardPreviewPanel,
    PREVIEW_MIN_WIDTH,
    build_preview_splitter,
    card_images_enabled,
)
from mtg_rebuilder.ui.widgets.chip_bar import Chip, ChipBar
from mtg_rebuilder.ui.widgets.edition_picker import CopyEditionTable, EditionComboBox
from mtg_rebuilder.ui.widgets.import_dialogs import AddInventoryListDialog, QuantityStepper
from mtg_rebuilder.ui.widgets.inventory_card_details import InventoryCardDetails
from mtg_rebuilder.ui.widgets.inventory_filter_panel import InventoryFilterDialog
from mtg_rebuilder.ui.widgets.inventory_image_grid import InventoryImageGrid

ORACLE_ID_ROLE = Qt.ItemDataRole.UserRole
SEARCH_DEBOUNCE_MS = 350
# Inventory Scryfall-syntax search (checkbox + logo). Hidden for now — local
# Filter dialog covers type / id≤ / CMC. Flip to True to re-enable the UI.
SCRYFALL_INVENTORY_SEARCH_ENABLED = False

COL_NAME = 0
COL_CMC = 1
COL_COLOR = 2
COL_RARITY = 3
COL_EDITION = 4
COL_TOTAL = 5
COL_FREE = 6
COL_ASSIGNED = 7
COL_DECKS = 8


class InventorySearchWorker(QThread):
    finished_ok = Signal(object, object)  # query_text, oracle_ids set
    failed = Signal(object, object)  # query_text, error message

    def __init__(
        self,
        query_text: str,
        inventory_ids: set[str],
        parent: QWidget | None = None,
    ) -> None:
        # Do not parent to a QWidget — keeps thread lifetime independent of UI.
        super().__init__(parent)
        self._query_text = query_text
        self._inventory_ids = inventory_ids

    def run(self) -> None:
        client = ScryfallClient()
        try:
            oracle_ids = client.search_oracle_ids_in(
                self._query_text, self._inventory_ids, max_pages=15
            )
            if self.isInterruptionRequested():
                return
            self.finished_ok.emit(self._query_text, oracle_ids)
        except Exception as exc:
            if not self.isInterruptionRequested():
                self.failed.emit(self._query_text, str(exc))
        finally:
            client.close()


class AddInventoryCardDialog(QDialog):
    def __init__(self, translator: Translator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._translator = translator
        self._results: list[CardSummary] = []
        self._selected: CardSummary | None = None
        self._quantity = 0
        self.setWindowTitle(self._translator.t("inventory.add_dialog.title"))
        self._preview: CardPreviewPanel | None = None
        self.resize(880 if card_images_enabled() else 560, 520)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self._search = QLineEdit()
        self._search.setPlaceholderText(
            self._translator.t("inventory.add_dialog.search")
        )
        self._search.textChanged.connect(self._refresh_results)
        self._search.returnPressed.connect(self._refresh_results)
        layout.addWidget(self._search)

        self._results_list = QListWidget()
        self._results_list.currentRowChanged.connect(self._on_result_selected)
        if card_images_enabled():
            self._preview = CardPreviewPanel(self._translator)
            layout.addWidget(build_preview_splitter(self._results_list, self._preview))
        else:
            layout.addWidget(self._results_list)

        form = QFormLayout()
        self._qty = QuantityStepper(99)
        self._qty.setMinimum(1)
        self._qty.setValue(1)
        form.addRow(self._translator.t("inventory.add_dialog.copies"), self._qty)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok is not None:
            ok.setText(self._translator.t("inventory.add_dialog.confirm"))
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _refresh_results(self) -> None:
        search = self._search.text().strip()
        with get_session() as session:
            cards = BrowseService(session).list_cards(search) if search else []
        self._results = [
            card
            for card in cards
            if not card.is_token and not card.is_basic_land
        ][:80]
        self._results_list.clear()
        for card in self._results:
            owned = f" · {card.copy_count}" if card.copy_count else ""
            self._results_list.addItem(f"{card.name}{owned}")

    def _selected_card(self) -> CardSummary | None:
        row = self._results_list.currentRow()
        if row < 0 or row >= len(self._results):
            return None
        return self._results[row]

    def _on_result_selected(self) -> None:
        if self._preview is None:
            return
        card = self._selected_card()
        if card is None:
            self._preview.clear()
        else:
            self._preview.set_card(card.oracle_id, card.name)

    def _accept(self) -> None:
        card = self._selected_card()
        if card is None:
            QMessageBox.warning(
                self,
                self._translator.t("common.error"),
                self._translator.t("inventory.add_dialog.no_selection"),
            )
            return
        self._selected = card
        self._quantity = self._qty.value()
        self.accept()

    def selected_card(self) -> CardSummary | None:
        return self._selected

    def quantity(self) -> int:
        return self._quantity


class EditInventoryCopiesDialog(QDialog):
    def __init__(
        self,
        translator: Translator,
        row: InventorySummaryRow,
        copies: list[CopyDetail] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._translator = translator
        self._row = row
        self._total = row.total_copies
        self._copies = copies or []
        self._editions: dict[int, str | None] = {}
        assigned = row.total_copies - row.free_copies
        self.setWindowTitle(self._translator.t("inventory.edit_dialog.title"))
        self.resize(480, 420 if self._copies else 200)
        self._build_ui(assigned)

    def _build_ui(self, assigned: int) -> None:
        layout = QVBoxLayout(self)

        form = QFormLayout()
        form.addRow(
            self._translator.t("inventory.edit_dialog.card"),
            QLabel(self._row.card_name),
        )
        self._qty = QuantityStepper(max(self._row.total_copies + 99, assigned + 99))
        self._qty.setMinimum(assigned)
        self._qty.setValue(self._row.total_copies)
        form.addRow(self._translator.t("inventory.edit_dialog.total"), self._qty)
        layout.addLayout(form)

        if assigned > 0:
            note = QLabel(
                self._translator.t("inventory.edit_dialog.assigned_note").format(
                    count=assigned
                )
            )
            note.setWordWrap(True)
            layout.addWidget(note)

        self._edition_table: CopyEditionTable | None = None
        if self._copies:
            group = QGroupBox(self._translator.t("inventory.editions.title"))
            group_layout = QVBoxLayout(group)
            hint = QLabel(self._translator.t("inventory.editions.hint"))
            hint.setWordWrap(True)
            group_layout.addWidget(hint)

            self._edition_table = CopyEditionTable(self._translator)
            self._edition_table.set_copies(
                [
                    (
                        copy.copy_id,
                        copy.oracle_id,
                        self._copy_label(number, copy),
                        copy.edition,
                    )
                    for number, copy in enumerate(self._copies, start=1)
                ]
            )
            group_layout.addWidget(self._edition_table, 1)

            apply_row = QHBoxLayout()
            self._apply_all_combo = EditionComboBox(
                self._row.oracle_id, None, self._translator
            )
            self._apply_all_button = QPushButton(
                self._translator.t("inventory.editions.apply_all")
            )
            self._apply_all_button.clicked.connect(self._apply_edition_to_all)
            apply_row.addWidget(self._apply_all_combo, 1)
            apply_row.addWidget(self._apply_all_button)
            group_layout.addLayout(apply_row)
            layout.addWidget(group, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _copy_label(self, number: int, copy: CopyDetail) -> str:
        where = copy.deck_name or self._translator.t("browse.inventory.free")
        return self._translator.t("inventory.editions.copy_label").format(
            number=number, where=where
        )

    def _apply_edition_to_all(self) -> None:
        if self._edition_table is not None:
            self._edition_table.apply_to_all(self._apply_all_combo.edition())

    def _accept(self) -> None:
        self._total = self._qty.value()
        if self._edition_table is not None:
            self._editions = self._edition_table.editions()
        self.accept()

    def total_copies(self) -> int:
        return self._total

    def copy_editions(self) -> dict[int, str | None]:
        return self._editions


class InventoryWidget(QWidget):
    changed = Signal()

    def __init__(self, translator: Translator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._translator = translator
        self._rows: list[InventorySummaryRow] = []
        self._visible_rows: list[InventorySummaryRow] = []
        self._sort_column = COL_NAME
        self._sort_ascending = True
        self._search_worker: InventorySearchWorker | None = None
        self._scryfall_oracle_ids: set[str] | None = None
        self._scryfall_query_applied: str = ""
        self._scryfall_busy = False
        self._search_generation = 0
        self._ignore_scryfall_button = False
        with get_session() as session:
            settings = SettingsService(session)
            self._show_card_images = settings.get_show_card_images()
            self._track_editions = settings.get_track_editions()
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(SEARCH_DEBOUNCE_MS)
        self._search_timer.timeout.connect(self._populate_table)
        self._needs_reload = False
        self._image_view_active = False
        self._build_ui()
        self.refresh()

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 (Qt override)
        super().showEvent(event)
        if self._needs_reload:
            self._reload()

    def set_show_card_images(self, enabled: bool) -> None:
        self._show_card_images = enabled
        self._preview_column.setVisible(enabled)
        self._image_view_button.setVisible(enabled)
        if not enabled and self._image_view_active:
            self._set_image_view(False)
        else:
            self._update_image_sort_visibility()

    def set_track_editions(self, enabled: bool) -> None:
        self._track_editions = enabled
        self._table.setColumnHidden(COL_EDITION, not enabled)
        self._details.set_track_editions(enabled)
        if self._sort_column == COL_EDITION and not enabled:
            self._sort_column = COL_NAME
            self._sort_ascending = True
        self._retranslate_image_sort()
        self.refresh()

    def retranslate(self) -> None:
        self._update_search_placeholder()
        self._update_filter_button()
        self._update_image_view_button()
        self._retranslate_image_sort()
        self._filter_dialog.retranslate()
        if SCRYFALL_INVENTORY_SEARCH_ENABLED:
            self._scryfall_mode.setText(
                self._translator.t("inventory.search.scryfall_mode")
            )
            self._scryfall_mode.setToolTip(
                self._translator.t("inventory.search.scryfall_mode_tip")
            )
            self._scryfall_button.setToolTip(
                self._translator.t("inventory.search.scryfall_run")
            )
        self._add_button.setText(self._translator.t("inventory.add_new"))
        self._add_list_button.setText(self._translator.t("inventory.add_list"))
        self._edit_button.setText(self._translator.t("inventory.edit_copies"))
        self._add_list_group.setTitle(self._translator.t("inventory.add_list.title"))
        self._import_text.setPlaceholderText(
            self._translator.t("inventory.add_list.placeholder")
        )
        self._load_file_button.setText(self._translator.t("decks.load_file"))
        self._submit_list_button.setText(self._translator.t("decks.submit_import"))
        self._cancel_list_button.setText(self._translator.t("decks.cancel_import"))
        self._table.setHorizontalHeaderLabels(self._header_labels())
        self._apply_header_tooltips()
        self._preview.retranslate()
        self._details.retranslate()
        self._image_grid.retranslate()
        self._update_search_hint()
        self._populate_table()

    def _header_labels(self) -> list[str]:
        return [
            self._translator.t("browse.cards.name"),
            self._translator.t("inventory.table.cmc"),
            self._translator.t("inventory.table.color"),
            self._translator.t("inventory.table.rarity"),
            self._translator.t("inventory.table.edition"),
            self._translator.t("inventory.table.total"),
            self._translator.t("inventory.table.free"),
            self._translator.t("inventory.table.assigned"),
            self._translator.t("inventory.table.decks"),
        ]

    def _apply_header_tooltips(self) -> None:
        header = self._table.horizontalHeaderItem(COL_CMC)
        if header is not None:
            header.setToolTip(self._translator.t("inventory.table.cmc_tip"))
        rarity = self._table.horizontalHeaderItem(COL_RARITY)
        if rarity is not None:
            rarity.setToolTip(self._translator.t("inventory.table.rarity_tip"))

    def _build_ui(self) -> None:
        self._main_layout = QVBoxLayout(self)

        self._collection_panel = QWidget()
        collection = QVBoxLayout(self._collection_panel)
        collection.setContentsMargins(0, 0, 0, 0)

        search_row = QHBoxLayout()
        self._search = QLineEdit()
        self._search.textChanged.connect(self._on_search_text_changed)
        search_row.addWidget(self._search, 1)

        # Checkbox before the run button so enabling the button mid-click
        # cannot steal the mouse release (layout-shift click-through).
        self._scryfall_mode = QCheckBox()
        self._scryfall_mode.toggled.connect(self._on_scryfall_mode_toggled)
        search_row.addWidget(self._scryfall_mode)

        self._scryfall_button = QToolButton()
        # Warm both variants so the first checkbox toggle never paints.
        scryfall_icon(22, active=False)
        scryfall_icon(22, active=True)
        self._scryfall_button.setIcon(scryfall_icon(22, active=False))
        self._scryfall_button.setIconSize(QSize(28, 28))
        self._scryfall_button.setAutoRaise(True)
        self._scryfall_button.setEnabled(False)
        self._scryfall_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._scryfall_button.clicked.connect(self._run_scryfall_search)
        search_row.addWidget(self._scryfall_button)
        if not SCRYFALL_INVENTORY_SEARCH_ENABLED:
            self._scryfall_mode.hide()
            self._scryfall_button.hide()
        collection.addLayout(search_row)

        self._search_hint = QLabel("")
        self._search_hint.setWordWrap(True)
        self._search_hint.setVisible(False)
        hint_font = self._search_hint.font()
        hint_font.setPointSize(max(8, hint_font.pointSize() - 1))
        self._search_hint.setFont(hint_font)
        collection.addWidget(self._search_hint)
        if not SCRYFALL_INVENTORY_SEARCH_ENABLED:
            self._search_hint.hide()

        actions = QHBoxLayout()
        self._filter_button = QPushButton()
        self._filter_button.clicked.connect(self._open_filters)
        actions.addWidget(self._filter_button)

        self._image_view_button = QPushButton()
        self._image_view_button.setCheckable(True)
        self._image_view_button.clicked.connect(self._toggle_image_view)
        self._image_view_button.setVisible(self._show_card_images)
        actions.addWidget(self._image_view_button)

        self._image_sort_label = QLabel()
        actions.addWidget(self._image_sort_label)
        self._image_sort_combo = QComboBox()
        configure_data_combo(self._image_sort_combo, min_contents=14)
        self._image_sort_combo.currentIndexChanged.connect(self._on_image_sort_changed)
        actions.addWidget(self._image_sort_combo)
        self._image_sort_dir_button = QPushButton()
        self._image_sort_dir_button.clicked.connect(self._toggle_image_sort_direction)
        actions.addWidget(self._image_sort_dir_button)
        self._update_image_sort_visibility()

        self._edit_button = QPushButton()
        self._edit_button.clicked.connect(self._edit_copies)
        self._edit_button.setVisible(False)
        actions.addWidget(self._edit_button)
        actions.addStretch()

        self._add_button = QPushButton()
        self._add_button.clicked.connect(self._add_card)
        actions.addWidget(self._add_button)

        self._add_list_button = QPushButton()
        self._add_list_button.clicked.connect(self._show_add_list_section)
        actions.addWidget(self._add_list_button)
        collection.addLayout(actions)

        self._filter_dialog = InventoryFilterDialog(self._translator, self)
        self._filter_dialog.filters_changed.connect(self._on_filters_changed)

        # Active filters as chips, so they can be read and dropped without
        # reopening the dialog.
        self._filter_chips = ChipBar()
        self._filter_chips.chip_removed.connect(self._on_filter_chip_removed)
        self._filter_chips.cleared.connect(self._filter_dialog.clear_filters)
        self._filter_chips.setVisible(False)
        collection.addWidget(self._filter_chips)

        self._table = QTableWidget(0, 9)
        self._table.setHorizontalHeaderLabels(self._header_labels())
        self._apply_header_tooltips()
        # Wide enough for five WUBRG pips side-by-side in the Colors column.
        self._table.setIconSize(QSize(74, 14))
        self._table.setColumnHidden(COL_EDITION, not self._track_editions)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        header = self._table.horizontalHeader()
        header.setStretchLastSection(False)
        # Fixed/Interactive only — ResizeToContents rescans every cell on each
        # rebuild and freezes the UI with ~1.5k inventory rows when visible.
        header.setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_CMC, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(COL_COLOR, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(COL_RARITY, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(COL_EDITION, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(COL_TOTAL, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(COL_FREE, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(COL_ASSIGNED, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(COL_DECKS, QHeaderView.ResizeMode.Interactive)
        header.setMinimumSectionSize(60)
        header.resizeSection(COL_CMC, 56)
        header.resizeSection(COL_COLOR, 88)
        header.resizeSection(COL_RARITY, 56)
        header.resizeSection(COL_EDITION, 110)
        header.resizeSection(COL_TOTAL, 64)
        header.resizeSection(COL_FREE, 64)
        header.resizeSection(COL_ASSIGNED, 80)
        header.resizeSection(COL_DECKS, 220)
        header.setSortIndicatorShown(True)
        header.setSortIndicator(COL_NAME, Qt.SortOrder.AscendingOrder)
        header.sectionClicked.connect(self._on_header_clicked)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)

        self._image_grid = InventoryImageGrid(self._translator)
        self._image_grid.card_selected.connect(self._on_grid_card_selected)

        self._view_stack = QStackedWidget()
        self._view_stack.addWidget(self._table)
        self._view_stack.addWidget(self._image_grid)

        self._preview = CardPreviewPanel(self._translator)
        self._details = InventoryCardDetails(self._translator)
        self._details.set_track_editions(self._track_editions)

        self._preview_column = QWidget()
        preview_layout = QVBoxLayout(self._preview_column)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(0)
        preview_layout.addWidget(self._preview, 1)
        preview_layout.addWidget(self._details, 0)
        self._preview_column.setMinimumWidth(PREVIEW_MIN_WIDTH)
        self._preview_column.setVisible(self._show_card_images)

        # Stretch 1 so the leftover height lands here: without it Qt splits it
        # between the splitter and the chip bar (Minimum policy = may grow),
        # leaving a tall empty band under the chips whenever a filter is active.
        collection.addWidget(
            build_preview_splitter(self._view_stack, self._preview_column), 1
        )

        self._main_layout.addWidget(self._collection_panel, 1)

        self._add_list_group = QGroupBox()
        import_layout = QVBoxLayout(self._add_list_group)

        self._import_text = QTextEdit()
        import_layout.addWidget(self._import_text, 1)

        import_buttons = QHBoxLayout()
        self._load_file_button = QPushButton()
        self._load_file_button.clicked.connect(self._load_list_file)
        self._submit_list_button = QPushButton()
        self._submit_list_button.clicked.connect(self._confirm_add_list)
        self._cancel_list_button = QPushButton()
        self._cancel_list_button.clicked.connect(self._hide_add_list_section)
        import_buttons.addWidget(self._load_file_button)
        import_buttons.addWidget(self._submit_list_button)
        import_buttons.addWidget(self._cancel_list_button)
        import_buttons.addStretch()
        import_layout.addLayout(import_buttons)

        self._add_list_group.setVisible(False)
        self._main_layout.addWidget(self._add_list_group, 0)

        self.retranslate()
        self._update_search_placeholder()
        self._sync_scryfall_controls()

    def _show_add_list_section(self) -> None:
        self._collection_panel.setVisible(False)
        self._add_list_group.setVisible(True)
        self._main_layout.setStretchFactor(self._collection_panel, 0)
        self._main_layout.setStretchFactor(self._add_list_group, 1)
        self._import_text.setFocus()

    def _hide_add_list_section(self) -> None:
        self._add_list_group.setVisible(False)
        self._collection_panel.setVisible(True)
        self._main_layout.setStretchFactor(self._add_list_group, 0)
        self._main_layout.setStretchFactor(self._collection_panel, 1)

    def refresh(self) -> None:
        """Reload inventory rows. Defers work while this tab is hidden."""
        if not self.isVisible():
            self._needs_reload = True
            return
        self._reload()

    def _reload(self) -> None:
        self._needs_reload = False
        with get_session() as session:
            self._rows = BrowseService(session).list_inventory(
                include_editions=self._track_editions
            )
            armed = [
                (deck.id, deck.name)
                for deck in DeckService(session).list_decks(status=DeckStatus.ARMED)
            ]
        self._filter_dialog.set_armed_decks(armed)
        self._filter_dialog.set_subtypes(
            subtype_catalog([row.type_line for row in self._rows])
        )
        self._populate_table()

    def _on_header_clicked(self, column: int) -> None:
        if column == self._sort_column:
            ascending = not self._sort_ascending
        else:
            # Numbers: high → low first; text: A → Z first
            ascending = column in (
                COL_NAME,
                COL_COLOR,
                COL_RARITY,
                COL_EDITION,
                COL_DECKS,
            )
        self._set_sort(column, ascending=ascending)

    def _set_sort(self, column: int, *, ascending: bool) -> None:
        self._sort_column = column
        self._sort_ascending = ascending
        header = self._table.horizontalHeader()
        order = (
            Qt.SortOrder.AscendingOrder
            if self._sort_ascending
            else Qt.SortOrder.DescendingOrder
        )
        header.setSortIndicator(column, order)
        self._sync_image_sort_controls()
        self._populate_table()

    def _default_ascending_for_column(self, column: int) -> bool:
        return column in (
            COL_NAME,
            COL_COLOR,
            COL_RARITY,
            COL_EDITION,
            COL_DECKS,
        )

    def _retranslate_image_sort(self) -> None:
        self._image_sort_label.setText(
            self._translator.t("inventory.view.sort_by")
        )
        current = self._image_sort_combo.currentData()
        labels = self._header_labels()
        options: list[tuple[int, str]] = [
            (COL_NAME, labels[COL_NAME]),
            (COL_CMC, labels[COL_CMC]),
            (COL_COLOR, labels[COL_COLOR]),
            (COL_RARITY, labels[COL_RARITY]),
        ]
        if self._track_editions:
            options.append((COL_EDITION, labels[COL_EDITION]))
        options.extend(
            [
                (COL_TOTAL, labels[COL_TOTAL]),
                (COL_FREE, labels[COL_FREE]),
                (COL_ASSIGNED, labels[COL_ASSIGNED]),
                (COL_DECKS, labels[COL_DECKS]),
            ]
        )
        self._image_sort_combo.blockSignals(True)
        self._image_sort_combo.clear()
        for column, label in options:
            self._image_sort_combo.addItem(label, column)
        preferred = (
            current
            if isinstance(current, int)
            else self._sort_column
        )
        if preferred == COL_EDITION and not self._track_editions:
            preferred = COL_NAME
        index = self._image_sort_combo.findData(preferred)
        self._image_sort_combo.setCurrentIndex(index if index >= 0 else 0)
        self._image_sort_combo.blockSignals(False)
        self._update_image_sort_dir_button()

    def _sync_image_sort_controls(self) -> None:
        column = self._sort_column
        if column == COL_EDITION and not self._track_editions:
            column = COL_NAME
        index = self._image_sort_combo.findData(column)
        self._image_sort_combo.blockSignals(True)
        if index >= 0:
            self._image_sort_combo.setCurrentIndex(index)
        self._image_sort_combo.blockSignals(False)
        self._update_image_sort_dir_button()

    def _update_image_sort_dir_button(self) -> None:
        key = (
            "decks.sort.asc" if self._sort_ascending else "decks.sort.desc"
        )
        self._image_sort_dir_button.setText(self._translator.t(key))

    def _update_image_sort_visibility(self) -> None:
        visible = self._image_view_active and self._show_card_images
        self._image_sort_label.setVisible(visible)
        self._image_sort_combo.setVisible(visible)
        self._image_sort_dir_button.setVisible(visible)

    def _on_image_sort_changed(self) -> None:
        data = self._image_sort_combo.currentData()
        if not isinstance(data, int):
            return
        if data == self._sort_column:
            return
        self._set_sort(data, ascending=self._default_ascending_for_column(data))

    def _toggle_image_sort_direction(self) -> None:
        self._set_sort(
            self._sort_column, ascending=not self._sort_ascending
        )

    def _sort_key(self, row: InventorySummaryRow):
        assigned = row.total_copies - row.free_copies
        if self._sort_column == COL_NAME:
            return row.card_name.casefold()
        if self._sort_column == COL_CMC:
            return -1.0 if row.cmc is None else float(row.cmc)
        if self._sort_column == COL_COLOR:
            return (row.color_identity or "").casefold()
        if self._sort_column == COL_RARITY:
            return rarity_sort_rank(row)
        if self._sort_column == COL_EDITION:
            return format_edition_summary(row).casefold()
        if self._sort_column == COL_TOTAL:
            return row.total_copies
        if self._sort_column == COL_FREE:
            return row.free_copies
        if self._sort_column == COL_ASSIGNED:
            return assigned
        if self._sort_column == COL_DECKS:
            return ", ".join(row.assigned_decks).casefold()
        return row.card_name.casefold()

    def _on_search_text_changed(self) -> None:
        if (
            SCRYFALL_INVENTORY_SEARCH_ENABLED
            and self._scryfall_mode.isChecked()
        ):
            self._sync_scryfall_controls()
            current = self._search.text().strip()
            if not current:
                self._clear_scryfall_results()
                self._update_search_hint()
                self._populate_table()
            elif (
                self._scryfall_oracle_ids is not None
                and current != self._scryfall_query_applied
            ):
                # Text diverged from the last API result — wait for logo click.
                self._scryfall_oracle_ids = None
                self._scryfall_query_applied = ""
                self._update_search_hint()
                self._populate_table()
            else:
                self._update_search_hint()
            return
        self._search_timer.start()

    def _open_filters(self) -> None:
        with get_session() as session:
            armed = [
                (deck.id, deck.name)
                for deck in DeckService(session).list_decks(status=DeckStatus.ARMED)
            ]
        self._filter_dialog.set_armed_decks(armed)
        self._filter_dialog.set_subtypes(
            subtype_catalog([row.type_line for row in self._rows])
        )
        self._filter_dialog.retranslate()
        self._filter_dialog.show()
        self._filter_dialog.raise_()
        self._filter_dialog.activateWindow()

    def _on_filters_changed(self) -> None:
        self._update_filter_button()
        self._populate_table()

    def _on_filter_chip_removed(self, key: object) -> None:
        if isinstance(key, FilterChip):
            self._filter_dialog.remove_chip(key)

    def _update_filter_button(self) -> None:
        state = self._filter_dialog.filter_state()
        self._filter_button.setText(
            format_filter_button_label(state, self._translator)
        )
        self._filter_chips.set_texts(
            remove_tooltip=self._translator.t("inventory.filters.chip_remove_tip"),
            clear_text=self._translator.t("inventory.filters.chips_clear"),
        )
        self._filter_chips.set_chips(
            [
                Chip(key=chip, label=label)
                for chip, label in format_filter_chips(
                    state,
                    self._translator,
                    self._filter_dialog.selected_deck_names(),
                )
            ]
        )

    def _update_image_view_button(self) -> None:
        key = (
            "inventory.view.images_active"
            if self._image_view_active
            else "inventory.view.images"
        )
        self._image_view_button.setText(self._translator.t(key))
        self._image_view_button.setChecked(self._image_view_active)

    def _toggle_image_view(self) -> None:
        self._set_image_view(self._image_view_button.isChecked())

    def _set_image_view(self, active: bool) -> None:
        selected = self._selected_row()
        selected_id = selected.oracle_id if selected is not None else None
        self._image_view_active = active
        self._view_stack.setCurrentWidget(
            self._image_grid if active else self._table
        )
        self._update_image_view_button()
        self._update_image_sort_visibility()
        if active:
            # Keep the same order already shown in the table (_visible_rows).
            self._sync_image_sort_controls()
            self._image_grid.set_rows(self._visible_rows)
            self._image_grid.select_oracle_id(selected_id)
            self._apply_selection(selected)
            # Stacked switch / empty preview often lay out a tick later — sync twice.
            QTimer.singleShot(0, self._finish_image_view_switch)
        else:
            if selected_id is not None:
                self._select_table_oracle_id(selected_id)
            else:
                self._apply_selection(None)

    def _finish_image_view_switch(self) -> None:
        self._image_grid.ensure_layout_sync()
        self._image_grid.setFocus()

    def _on_grid_card_selected(self, oracle_id: str) -> None:
        row = next((r for r in self._visible_rows if r.oracle_id == oracle_id), None)
        self._apply_selection(row)
        # Keep table selection in sync for when the user switches back.
        self._select_table_oracle_id(oracle_id, emit=False)

    def _select_table_oracle_id(
        self, oracle_id: str, *, emit: bool = True
    ) -> None:
        for index, row in enumerate(self._visible_rows):
            if row.oracle_id != oracle_id:
                continue
            if not emit:
                self._table.blockSignals(True)
            try:
                self._table.selectRow(index)
            finally:
                if not emit:
                    self._table.blockSignals(False)
            return
        if not emit:
            self._table.blockSignals(True)
        try:
            self._table.clearSelection()
        finally:
            if not emit:
                self._table.blockSignals(False)

    def _on_scryfall_mode_toggled(self, checked: bool) -> None:
        """Toggle mode only — never hits the Scryfall API here."""
        if not SCRYFALL_INVENTORY_SEARCH_ENABLED:
            return
        self._search_timer.stop()
        self._abandon_scryfall_worker()
        self._clear_scryfall_results()
        # Ignore accidental click-through onto the run button while the
        # checkbox click is still being delivered / layout is settling.
        self._ignore_scryfall_button = True
        self._scryfall_button.setEnabled(False)
        self._scryfall_button.setIcon(scryfall_icon(22, active=checked))
        self._update_search_placeholder()
        self._update_search_hint()
        # Defer so the checkbox paints before any table work.
        QTimer.singleShot(0, lambda: self._after_scryfall_mode_toggled(checked))

    def _after_scryfall_mode_toggled(self, checked: bool) -> None:
        if checked != self._scryfall_mode.isChecked():
            return
        self._ignore_scryfall_button = False
        self._sync_scryfall_controls()
        if not checked:
            # Re-apply name filter (may differ from the full list shown in mode).
            self._search_timer.start()
            return
        # Entering Scryfall mode ignores the name box until the logo runs.
        # Rebuild only when a name filter was active (otherwise the table
        # already shows the full panel-filtered collection).
        if self._search.text().strip():
            self._populate_table()

    def _update_search_placeholder(self) -> None:
        if (
            SCRYFALL_INVENTORY_SEARCH_ENABLED
            and self._scryfall_mode.isChecked()
        ):
            self._search.setPlaceholderText(
                self._translator.t("inventory.search.scryfall")
            )
        else:
            self._search.setPlaceholderText(
                self._translator.t("inventory.search.name")
            )

    def _sync_scryfall_controls(self) -> None:
        if not SCRYFALL_INVENTORY_SEARCH_ENABLED:
            return
        mode_on = self._scryfall_mode.isChecked()
        self._scryfall_button.setIcon(scryfall_icon(22, active=mode_on))
        if self._ignore_scryfall_button or self._scryfall_busy:
            self._scryfall_button.setEnabled(False)
            return
        has_query = bool(self._search.text().strip())
        self._scryfall_button.setEnabled(mode_on and has_query)

    def _clear_scryfall_results(self) -> None:
        self._scryfall_oracle_ids = None
        self._scryfall_query_applied = ""
        self._search_generation += 1

    def _abandon_scryfall_worker(self) -> None:
        worker = self._search_worker
        self._search_worker = None
        self._scryfall_busy = False
        if worker is None:
            return
        try:
            worker.finished_ok.disconnect()
        except RuntimeError:
            pass
        try:
            worker.failed.disconnect()
        except RuntimeError:
            pass
        worker.requestInterruption()
        if worker.isRunning():
            # Keep the QThread object alive until it finishes so Qt does not
            # destroy a running thread (which can wedge the process).
            worker.finished.connect(worker.deleteLater)
        else:
            worker.deleteLater()

    def _update_search_hint(self) -> None:
        if not SCRYFALL_INVENTORY_SEARCH_ENABLED:
            self._search_hint.clear()
            self._search_hint.setVisible(False)
            return
        if self._scryfall_busy:
            self._search_hint.setText(self._translator.t("inventory.search.scryfall_busy"))
            self._search_hint.setVisible(True)
            return
        if self._scryfall_mode.isChecked() and self._scryfall_query_applied:
            self._search_hint.setText(
                self._translator.t("inventory.search.scryfall_applied").format(
                    query=self._scryfall_query_applied,
                    count=len(self._scryfall_oracle_ids or ()),
                )
            )
            self._search_hint.setVisible(True)
            return
        if self._scryfall_mode.isChecked():
            self._search_hint.setText(
                self._translator.t("inventory.search.scryfall_idle")
            )
            self._search_hint.setVisible(True)
            return
        self._search_hint.clear()
        self._search_hint.setVisible(False)

    def _run_scryfall_search(self) -> None:
        if not SCRYFALL_INVENTORY_SEARCH_ENABLED:
            return
        if self._ignore_scryfall_button or self._scryfall_busy:
            return
        query_text = self._search.text().strip()
        if not query_text or not self._scryfall_mode.isChecked():
            return
        self._abandon_scryfall_worker()
        inventory_ids = {row.oracle_id for row in self._rows}
        self._search_generation += 1
        generation = self._search_generation
        self._scryfall_busy = True
        self._update_search_hint()
        self._sync_scryfall_controls()

        worker = InventorySearchWorker(query_text, inventory_ids)
        self._search_worker = worker

        def on_ok(done_query: object, oracle_ids: object) -> None:
            if generation != self._search_generation:
                return
            self._scryfall_busy = False
            self._search_worker = None
            if done_query != self._search.text().strip():
                self._sync_scryfall_controls()
                self._update_search_hint()
                return
            if not isinstance(oracle_ids, set):
                self._sync_scryfall_controls()
                self._update_search_hint()
                return
            self._scryfall_oracle_ids = oracle_ids
            self._scryfall_query_applied = str(done_query)
            self._update_search_hint()
            self._sync_scryfall_controls()
            self._populate_table()

        def on_fail(done_query: object, error: object) -> None:
            if generation != self._search_generation:
                return
            self._scryfall_busy = False
            self._search_worker = None
            self._scryfall_oracle_ids = None
            self._scryfall_query_applied = ""
            self._search_hint.setText(
                self._translator.t("inventory.search.scryfall_failed").format(
                    error=str(error)
                )
            )
            self._search_hint.setVisible(True)
            self._sync_scryfall_controls()
            self._populate_table()

        worker.finished_ok.connect(
            on_ok, Qt.ConnectionType.QueuedConnection
        )
        worker.failed.connect(on_fail, Qt.ConnectionType.QueuedConnection)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _populate_table(self) -> None:
        scryfall_mode = (
            SCRYFALL_INVENTORY_SEARCH_ENABLED and self._scryfall_mode.isChecked()
        )
        name_query = "" if scryfall_mode else self._search.text()
        scryfall_ids = self._scryfall_oracle_ids if scryfall_mode else None
        # In Scryfall mode with no query run yet, show the full collection
        # (still panel-filtered). After a query, intersect.
        filtered = filter_inventory_cards(
            self._rows,
            name_query=name_query,
            panel=self._filter_dialog.filter_state(),
            scryfall_oracle_ids=scryfall_ids,
        )
        rows = sorted(
            filtered, key=self._sort_key, reverse=not self._sort_ascending
        )
        self._visible_rows = list(rows)

        table = self._table
        header = table.horizontalHeader()
        # Guard: if any column is still ResizeToContents, pin it Fixed for the
        # bulk insert — otherwise Qt measures every cell and freezes (~1.5k rows).
        pinned: list[tuple[int, int]] = []
        for col in range(table.columnCount()):
            mode = header.sectionResizeMode(col)
            if mode == QHeaderView.ResizeMode.ResizeToContents:
                pinned.append((col, header.sectionSize(col)))
                header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)

        table.setUpdatesEnabled(False)
        table.blockSignals(True)
        try:
            table.setRowCount(len(rows))
            for index, row in enumerate(rows):
                assigned = row.total_copies - row.free_copies
                decks_text = format_inventory_decks(row, self._translator)

                name_item = QTableWidgetItem(row.card_name)
                name_item.setData(ORACLE_ID_ROLE, row.oracle_id)
                name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

                cmc_item = QTableWidgetItem(
                    format_mana_value(row.cmc, self._translator)
                )
                cmc_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                cmc_item.setFlags(cmc_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

                color_text = format_color_identity(
                    row.color_identity, self._translator
                )
                color_pix = color_identity_pixmap(row.color_identity, size=14)
                if color_pix is not None:
                    color_item = QTableWidgetItem()
                    color_item.setIcon(QIcon(color_pix))
                    color_item.setToolTip(color_text)
                else:
                    color_item = QTableWidgetItem(color_text)
                color_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                color_item.setFlags(
                    color_item.flags() & ~Qt.ItemFlag.ItemIsEditable
                )

                rarity_item = QTableWidgetItem(
                    format_rarity_summary(row, self._translator)
                )
                rarity_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                rarity_item.setFlags(
                    rarity_item.flags() & ~Qt.ItemFlag.ItemIsEditable
                )

                edition_item = QTableWidgetItem(format_edition_summary(row))
                edition_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                edition_item.setFlags(
                    edition_item.flags() & ~Qt.ItemFlag.ItemIsEditable
                )

                total_item = QTableWidgetItem(str(row.total_copies))
                total_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                total_item.setFlags(
                    total_item.flags() & ~Qt.ItemFlag.ItemIsEditable
                )

                free_item = QTableWidgetItem(str(row.free_copies))
                free_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                free_item.setFlags(free_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

                assigned_item = QTableWidgetItem(str(assigned))
                assigned_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                assigned_item.setFlags(
                    assigned_item.flags() & ~Qt.ItemFlag.ItemIsEditable
                )

                decks_item = QTableWidgetItem(decks_text)
                decks_item.setFlags(
                    decks_item.flags() & ~Qt.ItemFlag.ItemIsEditable
                )
                if row.assigned_decks:
                    decks_item.setToolTip("\n".join(row.assigned_decks))

                table.setItem(index, COL_NAME, name_item)
                table.setItem(index, COL_CMC, cmc_item)
                table.setItem(index, COL_COLOR, color_item)
                table.setItem(index, COL_RARITY, rarity_item)
                table.setItem(index, COL_EDITION, edition_item)
                table.setItem(index, COL_TOTAL, total_item)
                table.setItem(index, COL_FREE, free_item)
                table.setItem(index, COL_ASSIGNED, assigned_item)
                table.setItem(index, COL_DECKS, decks_item)
        finally:
            for col, width in pinned:
                header.resizeSection(col, width)
            table.blockSignals(False)
            table.setUpdatesEnabled(True)
        if self._image_view_active:
            selected_id = self._image_grid.selected_oracle_id()
            self._image_grid.set_rows(self._visible_rows)
            row = next(
                (r for r in self._visible_rows if r.oracle_id == selected_id),
                None,
            )
            if row is not None:
                self._image_grid.select_oracle_id(row.oracle_id)
                self._apply_selection(row)
            else:
                self._image_grid.select_oracle_id(None)
                self._apply_selection(None)
        else:
            self._on_selection_changed()

    def _selected_row(self) -> InventorySummaryRow | None:
        if self._image_view_active:
            oracle_id = self._image_grid.selected_oracle_id()
            if oracle_id is None:
                return None
            return next(
                (row for row in self._visible_rows if row.oracle_id == oracle_id),
                None,
            )
        selected = self._table.selectionModel().selectedRows()
        if not selected:
            return None
        index = selected[0].row()
        if index < 0 or index >= len(self._visible_rows):
            return None
        return self._visible_rows[index]

    def _on_selection_changed(self) -> None:
        self._apply_selection(self._selected_row())

    def _apply_selection(self, row: InventorySummaryRow | None) -> None:
        self._edit_button.setVisible(row is not None)
        if row is None:
            self._preview.clear()
            self._details.clear()
        else:
            self._preview.set_card(row.oracle_id, row.card_name)
            self._details.set_row(row)

    def _add_card(self) -> None:
        dialog = AddInventoryCardDialog(self._translator, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        card = dialog.selected_card()
        quantity = dialog.quantity()
        if card is None or quantity <= 0:
            return
        try:
            with get_session() as session:
                InventoryService(session).add_copy(card.oracle_id, quantity)
        except Exception as exc:
            QMessageBox.critical(
                self,
                self._translator.t("common.error"),
                str(exc),
            )
            return
        self.refresh()
        self.changed.emit()

    def _load_list_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            self._translator.t("inventory.add_list.dialog_title"),
            str(Path.home()),
            "Text files (*.txt *.dek);;MTGO decks (*.dek);;All files (*)",
        )
        if not path:
            return
        try:
            content = Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(
                self,
                self._translator.t("common.error"),
                str(exc),
            )
            return
        self._import_text.setPlainText(content)

    def _confirm_add_list(self) -> None:
        text = self._import_text.toPlainText().strip()
        if not text:
            QMessageBox.information(
                self,
                self._translator.t("inventory.add_list.title"),
                self._translator.t("inventory.add_list.empty"),
            )
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
            is_url = any(
                host in text.casefold() for host in ("moxfield", "archidekt")
            )
            QMessageBox.critical(
                self,
                self._translator.t("common.error"),
                format_deck_url_error(self._translator, exc)
                if is_url
                else str(exc),
            )
            return

        if not preview.identified and not preview.unresolved_lines:
            QMessageBox.information(
                self,
                self._translator.t("inventory.add_list.title"),
                self._translator.t("inventory.add_list.empty"),
            )
            return

        dialog = AddInventoryListDialog(
            self._translator,
            preview.identified,
            preview.unresolved_lines,
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        quantities = dialog.quantities()
        if not quantities:
            return
        set_codes = dialog.set_codes() if self._track_editions else {}
        try:
            with get_session() as session:
                inventory = InventoryService(session)
                for oracle_id, quantity in quantities.items():
                    inventory.add_copy(
                        oracle_id, quantity, edition=set_codes.get(oracle_id)
                    )
        except Exception as exc:
            QMessageBox.critical(
                self,
                self._translator.t("common.error"),
                str(exc),
            )
            return

        self._import_text.clear()
        self._hide_add_list_section()
        self.refresh()
        self.changed.emit()

    def _edit_copies(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        copies: list[CopyDetail] = []
        if self._track_editions:
            with get_session() as session:
                copies = InventoryService(session).list_copies_with_deck(row.oracle_id)
        dialog = EditInventoryCopiesDialog(self._translator, row, copies, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            with get_session() as session:
                inventory = InventoryService(session)
                editions = dialog.copy_editions()
                if editions:
                    inventory.set_copy_editions(editions)
                inventory.set_total_copies(row.oracle_id, dialog.total_copies())
        except Exception as exc:
            QMessageBox.critical(
                self,
                self._translator.t("common.error"),
                str(exc),
            )
            return
        self.refresh()
        self.changed.emit()
