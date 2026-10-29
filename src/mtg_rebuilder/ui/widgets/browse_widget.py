from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
import httpx

from mtg_rebuilder.config import (
    SCRYFALL_BULK_ORACLE_TYPE,
    SCRYFALL_BULK_UNIQUE_ARTWORK_TYPE,
    THEME_DARK,
    THEME_LIGHT,
    THEME_SYSTEM,
)
from mtg_rebuilder.database import get_session
from mtg_rebuilder.i18n import Translator
from mtg_rebuilder.ui.error_text import (
    format_scryfall_job_error,
    network_failure_token,
)
from mtg_rebuilder.ui.combo import configure_data_combo
from mtg_rebuilder.models.enums import ActivityCategory
from mtg_rebuilder.services import (
    ActivityService,
    BrowseService,
    CardImageService,
    HouseBanService,
    ScryfallBulkService,
    ScryfallService,
    SettingsService,
)
from mtg_rebuilder.ui.widgets.import_dialogs import CardPickDialog
from mtg_rebuilder.services.activity_service import (
    ActivityEventRow,
    HISTORY_PAGE_SIZE,
)
from mtg_rebuilder.services.card_image_service import ImageCacheStatus, ImageDownloadScope
from mtg_rebuilder.services.scryfall_bulk_service import BulkSyncStatus
from mtg_rebuilder.ui.inventory_display import (
    format_availability_status,
    format_inventory_decks,
)
from mtg_rebuilder.ui.widgets.card_preview import CardPreviewPanel, build_preview_splitter

INV_COL_NAME = 0
INV_COL_TOTAL = 1
INV_COL_FREE = 2
INV_COL_ASSIGNED = 3
INV_COL_DECKS = 4
CUSTOMIZE_SECTION_INDEX = 1
AVAILABILITY_SECTION_INDEX = 3
SCRYFALL_SECTION_INDEX = 5
CARD_ORACLE_ID_ROLE = Qt.ItemDataRole.UserRole
HOUSE_BAN_ORACLE_ROLE = Qt.ItemDataRole.UserRole


class BulkSyncWorker(QThread):
    progress = Signal(str)
    finished_ok = Signal(int, str)
    failed = Signal(str)

    def __init__(self, pack_type: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pack_type = pack_type

    def run(self) -> None:
        try:
            with get_session() as session:
                bulk = ScryfallBulkService(session)
                try:
                    result = bulk.sync_bulk(
                        self._pack_type, progress=self.progress.emit
                    )
                finally:
                    bulk.close()
            self.finished_ok.emit(result.imported_cards, result.pack_type)
        except httpx.HTTPError:
            self.failed.emit(network_failure_token())
        except Exception as exc:
            self.failed.emit(str(exc))


class CardDataRefreshWorker(QThread):
    progress = Signal(str)
    finished_ok = Signal(int)
    failed = Signal(str)

    def run(self) -> None:
        try:
            with get_session() as session:
                scryfall = ScryfallService(session)
                try:
                    count = scryfall.refresh_collection_card_data(
                        progress=self.progress.emit
                    )
                finally:
                    scryfall.close()
            self.finished_ok.emit(count)
        except httpx.HTTPError:
            self.failed.emit(network_failure_token())
        except Exception as exc:
            self.failed.emit(str(exc))


class ImageDownloadWorker(QThread):
    progress = Signal(str)
    finished_ok = Signal(int, int)
    failed = Signal(str)

    def __init__(
        self, scope: ImageDownloadScope, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._scope = scope

    def run(self) -> None:
        try:
            with get_session() as session:
                images = CardImageService(session)
                try:
                    result = images.download_images(
                        self._scope, progress=self.progress.emit
                    )
                finally:
                    images.close()
            self.finished_ok.emit(result.downloaded, result.skipped)
        except httpx.HTTPError:
            self.failed.emit(network_failure_token())
        except Exception as exc:
            self.failed.emit(str(exc))


class RemoteBulkStatusWorker(QThread):
    finished_ok = Signal(object)
    failed = Signal(str)

    def run(self) -> None:
        try:
            with get_session() as session:
                bulk = ScryfallBulkService(session)
                try:
                    status = bulk.check_remote_status()
                finally:
                    bulk.close()
            self.finished_ok.emit(status)
        except Exception as exc:
            self.failed.emit(str(exc))


class BrowseWidget(QWidget):
    changed = Signal()
    locale_changed = Signal(str)
    theme_changed = Signal(str)
    show_images_changed = Signal(bool)
    track_editions_changed = Signal(bool)
    warning_settings_changed = Signal()

    def __init__(self, translator: Translator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._translator = translator
        with get_session() as session:
            settings = SettingsService(session)
            self._show_card_images = settings.get_show_card_images()
            self._track_editions = settings.get_track_editions()
            self._show_legality_warnings = settings.get_show_legality_warnings()
            self._show_rule_warnings = settings.get_show_rule_warnings()
            self._ui_theme = settings.get_ui_theme()
        self._sync_worker: BulkSyncWorker | None = None
        self._card_data_worker: CardDataRefreshWorker | None = None
        self._image_worker: ImageDownloadWorker | None = None
        self._remote_worker: RemoteBulkStatusWorker | None = None
        self._bulk_status: BulkSyncStatus | None = None
        self._scryfall_busy = False
        self._availability_dirty = True
        self._scryfall_status_dirty = True
        self._build_ui()
        self.refresh()

    def retranslate(self) -> None:
        self._section_list.item(0).setText(self._translator.t("browse.section.overview"))
        self._section_list.item(1).setText(
            self._translator.t("browse.section.customize")
        )
        self._section_list.item(2).setText(self._translator.t("browse.section.cards"))
        self._section_list.item(3).setText(
            self._translator.t("browse.section.availability")
        )
        self._section_list.item(4).setText(
            self._translator.t("browse.section.history")
        )
        self._section_list.item(5).setText(
            self._translator.t("browse.section.scryfall")
        )
        self._card_search.setPlaceholderText(self._translator.t("browse.cards.search"))
        self._unique_button.setText(
            self._translator.t("browse.scryfall.sync_unique")
        )
        self._images_collection_button.setText(
            self._translator.t("browse.scryfall.images_collection")
        )
        self._images_cached_button.setText(
            self._translator.t("browse.scryfall.images_cached")
        )
        self._card_data_button.setText(
            self._translator.t("browse.scryfall.card_data_refresh")
        )
        self._scryfall_info.setText(self._translator.t("browse.scryfall.info"))
        self._update_oracle_button_label()
        self._language_label.setText(self._translator.t("config.language"))
        self._theme_label.setText(self._translator.t("config.theme"))
        self._inventory_summary_group.setTitle(
            self._translator.t("inventory.summary.title")
        )
        self._inventory_search.setPlaceholderText(
            self._translator.t("inventory.search.name")
        )
        self._inventory_hint.setText(self._translator.t("inventory.search.hint"))
        self._cards_table.setHorizontalHeaderLabels(
            [
                self._translator.t("browse.cards.name"),
                self._translator.t("browse.cards.type"),
                self._translator.t("browse.cards.cmc"),
                self._translator.t("browse.cards.copies"),
                self._translator.t("browse.cards.flags"),
            ]
        )
        self._card_refresh_button.setText(self._translator.t("common.refresh"))
        self._inventory_results_table.setHorizontalHeaderLabels(
            [
                self._translator.t("browse.cards.name"),
                self._translator.t("inventory.table.total"),
                self._translator.t("inventory.table.free"),
                self._translator.t("inventory.table.assigned"),
                self._translator.t("inventory.table.decks"),
            ]
        )
        self._history_filter_label.setText(self._translator.t("browse.history.filter"))
        self._sync_history_filter_combo()
        self._history_table.setHorizontalHeaderLabels(
            [
                self._translator.t("browse.history.when"),
                self._translator.t("browse.history.event"),
            ]
        )
        self._history_empty.setText(self._translator.t("browse.history.empty"))
        self._history_load_more.setText(
            self._translator.t("browse.history.load_more")
        )
        self._history_export.setText(self._translator.t("browse.history.export"))
        self._history_undo.setText(self._translator.t("browse.history.undo"))
        self._history_redo.setText(self._translator.t("browse.history.redo"))
        self._update_history_undo_redo_enabled()
        self._scryfall_group.setTitle(self._translator.t("browse.section.scryfall"))
        self._show_images_check.setText(
            self._translator.t("browse.customize.show_images")
        )
        self._welcome_separator.setText(
            self._translator.t("browse.overview.welcome_separator")
        )
        self._welcome_label.setText(self._translator.t("browse.overview.welcome"))
        self._track_editions_check.setText(
            self._translator.t("browse.customize.track_editions")
        )
        self._track_editions_check.setToolTip(
            self._translator.t("browse.customize.track_editions_hint")
        )
        self._show_legality_check.setText(
            self._translator.t("browse.customize.show_legality_warnings")
        )
        self._show_rules_check.setText(
            self._translator.t("browse.customize.show_rule_warnings")
        )
        self._house_ban_group.setTitle(
            self._translator.t("browse.customize.house_ban.title")
        )
        self._house_ban_hint.setText(
            self._translator.t("browse.customize.house_ban.hint")
        )
        self._house_ban_add.setText(
            self._translator.t("browse.customize.house_ban.add")
        )
        self._house_ban_remove.setText(
            self._translator.t("browse.customize.house_ban.remove")
        )
        self._display_group.setTitle(
            self._translator.t("browse.customize.display")
        )
        self._warnings_group.setTitle(
            self._translator.t("browse.customize.warnings")
        )
        self._card_preview.retranslate()
        self._sync_language_combo()
        self._sync_theme_combo()
        self._refresh_house_bans()
        self.refresh()

    @property
    def show_card_images(self) -> bool:
        return self._show_card_images

    @property
    def track_editions(self) -> bool:
        return self._track_editions

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        splitter = QSplitter()
        layout.addWidget(splitter)

        self._section_list = QListWidget()
        self._section_list.addItem(self._translator.t("browse.section.overview"))
        self._section_list.addItem(self._translator.t("browse.section.customize"))
        self._section_list.addItem(self._translator.t("browse.section.cards"))
        self._section_list.addItem(self._translator.t("browse.section.availability"))
        self._section_list.addItem(self._translator.t("browse.section.history"))
        self._section_list.addItem(self._translator.t("browse.section.scryfall"))
        splitter.addWidget(self._section_list)

        self._panels = QStackedWidget()
        splitter.addWidget(self._panels)
        splitter.setStretchFactor(1, 1)

        self._panels.addWidget(self._build_overview_panel())
        self._panels.addWidget(self._build_customize_panel())
        self._panels.addWidget(self._build_cards_panel())
        self._panels.addWidget(self._build_inventory_panel())
        self._panels.addWidget(self._build_history_panel())
        self._panels.addWidget(self._build_scryfall_panel())

        self._section_list.currentRowChanged.connect(self._on_section_changed)
        self._section_list.setCurrentRow(0)

    def _on_section_changed(self, index: int) -> None:
        self._panels.setCurrentIndex(index)
        if index == CUSTOMIZE_SECTION_INDEX:
            self._refresh_house_bans()
        if index == AVAILABILITY_SECTION_INDEX and self._availability_dirty:
            self._refresh_inventory()
        if index == SCRYFALL_SECTION_INDEX:
            if self._scryfall_status_dirty:
                self._refresh_scryfall_status()
            self._start_remote_status_check()

    def _build_overview_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        self._greeting_label = QLabel()
        self._greeting_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        greeting_font = QFont("Monospace")
        greeting_font.setStyleHint(QFont.StyleHint.Monospace)
        self._greeting_label.setFont(greeting_font)
        layout.addWidget(self._greeting_label)

        self._tagline_label = QLabel()
        self._tagline_label.setWordWrap(True)
        layout.addWidget(self._tagline_label)

        self._overview_label = QLabel()
        self._overview_label.setWordWrap(True)
        layout.addWidget(self._overview_label)

        self._welcome_separator = QLabel(
            self._translator.t("browse.overview.welcome_separator")
        )
        layout.addWidget(self._welcome_separator)

        self._welcome_label = QLabel(self._translator.t("browse.overview.welcome"))
        self._welcome_label.setWordWrap(True)
        self._welcome_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self._welcome_label)

        layout.addStretch()
        return panel

    def _build_customize_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        self._display_group = QGroupBox(self._translator.t("browse.customize.display"))
        display_layout = QVBoxLayout(self._display_group)

        self._track_editions_check = QCheckBox(
            self._translator.t("browse.customize.track_editions")
        )
        self._track_editions_check.setToolTip(
            self._translator.t("browse.customize.track_editions_hint")
        )
        self._track_editions_check.setChecked(self._track_editions)
        self._track_editions_check.toggled.connect(self._on_track_editions_toggled)
        display_layout.addWidget(self._track_editions_check)

        self._show_images_check = QCheckBox(
            self._translator.t("browse.customize.show_images")
        )
        self._show_images_check.setChecked(self._show_card_images)
        self._show_images_check.toggled.connect(self._on_show_images_toggled)
        display_layout.addWidget(self._show_images_check)

        # Flat form rows (no nested QGroupBox): on Windows the nested
        # Language/Theme boxes showed duplicate titles and zero-width combos.
        display_form = QFormLayout()
        display_form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )
        self._language_label = QLabel(self._translator.t("config.language"))
        self._language_combo = QComboBox()
        configure_data_combo(self._language_combo)
        self._language_combo.currentIndexChanged.connect(self._on_language_changed)
        display_form.addRow(self._language_label, self._language_combo)
        self._theme_label = QLabel(self._translator.t("config.theme"))
        self._theme_combo = QComboBox()
        configure_data_combo(self._theme_combo)
        self._theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        display_form.addRow(self._theme_label, self._theme_combo)
        display_layout.addLayout(display_form)
        layout.addWidget(self._display_group)

        self._warnings_group = QGroupBox(
            self._translator.t("browse.customize.warnings")
        )
        warnings_layout = QVBoxLayout(self._warnings_group)
        self._show_legality_check = QCheckBox(
            self._translator.t("browse.customize.show_legality_warnings")
        )
        self._show_legality_check.setChecked(self._show_legality_warnings)
        self._show_legality_check.toggled.connect(self._on_show_legality_toggled)
        warnings_layout.addWidget(self._show_legality_check)
        self._show_rules_check = QCheckBox(
            self._translator.t("browse.customize.show_rule_warnings")
        )
        self._show_rules_check.setChecked(self._show_rule_warnings)
        self._show_rules_check.toggled.connect(self._on_show_rules_toggled)
        warnings_layout.addWidget(self._show_rules_check)
        layout.addWidget(self._warnings_group)

        self._house_ban_group = QGroupBox(
            self._translator.t("browse.customize.house_ban.title")
        )
        ban_layout = QVBoxLayout(self._house_ban_group)
        self._house_ban_hint = QLabel(
            self._translator.t("browse.customize.house_ban.hint")
        )
        self._house_ban_hint.setWordWrap(True)
        ban_layout.addWidget(self._house_ban_hint)
        self._house_ban_list = QListWidget()
        ban_layout.addWidget(self._house_ban_list, 1)
        ban_actions = QHBoxLayout()
        self._house_ban_add = QPushButton(
            self._translator.t("browse.customize.house_ban.add")
        )
        self._house_ban_add.clicked.connect(self._add_house_ban)
        ban_actions.addWidget(self._house_ban_add)
        self._house_ban_remove = QPushButton(
            self._translator.t("browse.customize.house_ban.remove")
        )
        self._house_ban_remove.clicked.connect(self._remove_house_ban)
        ban_actions.addWidget(self._house_ban_remove)
        ban_actions.addStretch()
        ban_layout.addLayout(ban_actions)
        layout.addWidget(self._house_ban_group, 1)

        self._sync_language_combo()
        self._sync_theme_combo()
        self._refresh_house_bans()
        return panel

    def _on_track_editions_toggled(self, checked: bool) -> None:
        if checked == self._track_editions:
            return
        self._track_editions = checked
        with get_session() as session:
            SettingsService(session).set_track_editions(checked)
        self.track_editions_changed.emit(checked)

    def _on_show_images_toggled(self, checked: bool) -> None:
        if checked == self._show_card_images:
            return
        self._show_card_images = checked
        with get_session() as session:
            SettingsService(session).set_show_card_images(checked)
        self._card_preview.setVisible(checked)
        self.show_images_changed.emit(checked)

    def _on_show_legality_toggled(self, checked: bool) -> None:
        if checked == self._show_legality_warnings:
            return
        self._show_legality_warnings = checked
        with get_session() as session:
            SettingsService(session).set_show_legality_warnings(checked)
        self.warning_settings_changed.emit()

    def _on_show_rules_toggled(self, checked: bool) -> None:
        if checked == self._show_rule_warnings:
            return
        self._show_rule_warnings = checked
        with get_session() as session:
            SettingsService(session).set_show_rule_warnings(checked)
        self.warning_settings_changed.emit()

    def _refresh_house_bans(self) -> None:
        self._house_ban_list.clear()
        with get_session() as session:
            bans = HouseBanService(session).list_bans()
        for ban in bans:
            item = QListWidgetItem(ban.name)
            item.setData(HOUSE_BAN_ORACLE_ROLE, ban.oracle_id)
            self._house_ban_list.addItem(item)

    def _add_house_ban(self) -> None:
        dialog = CardPickDialog(
            self._translator,
            title=self._translator.t("browse.customize.house_ban.add"),
            max_quantity=1,
            show_available=False,
            parent=self,
        )
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        picked = dialog.result()
        if picked is None:
            return
        with get_session() as session:
            HouseBanService(session).add(picked.oracle_id, picked.name)
        self._refresh_house_bans()
        self.warning_settings_changed.emit()

    def _remove_house_ban(self) -> None:
        item = self._house_ban_list.currentItem()
        if item is None:
            return
        oracle_id = item.data(HOUSE_BAN_ORACLE_ROLE)
        if not isinstance(oracle_id, str) or not oracle_id:
            return
        with get_session() as session:
            HouseBanService(session).remove(oracle_id)
        self._refresh_house_bans()
        self.warning_settings_changed.emit()

    def _sync_language_combo(self) -> None:
        self._language_combo.blockSignals(True)
        self._language_combo.clear()
        for code, label_key in (("en", "language.en"), ("es", "language.es")):
            self._language_combo.addItem(self._translator.t(label_key), code)
        index = self._language_combo.findData(self._translator.locale)
        self._language_combo.setCurrentIndex(index if index >= 0 else 0)
        self._language_combo.blockSignals(False)

    def _on_language_changed(self) -> None:
        locale = self._language_combo.currentData()
        if isinstance(locale, str) and locale != self._translator.locale:
            self.locale_changed.emit(locale)

    def _sync_theme_combo(self) -> None:
        self._theme_combo.blockSignals(True)
        self._theme_combo.clear()
        for code, label_key in (
            (THEME_SYSTEM, "theme.system"),
            (THEME_LIGHT, "theme.light"),
            (THEME_DARK, "theme.dark"),
        ):
            self._theme_combo.addItem(self._translator.t(label_key), code)
        index = self._theme_combo.findData(self._ui_theme)
        self._theme_combo.setCurrentIndex(index if index >= 0 else 0)
        self._theme_combo.blockSignals(False)

    def _on_theme_changed(self) -> None:
        theme = self._theme_combo.currentData()
        if isinstance(theme, str) and theme != self._ui_theme:
            self._ui_theme = theme
            self.theme_changed.emit(theme)

    def _build_cards_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        search_row = QHBoxLayout()
        self._card_search = QLineEdit()
        self._card_search.setPlaceholderText(self._translator.t("browse.cards.search"))
        self._card_search.textChanged.connect(self._refresh_cards)
        self._card_search.returnPressed.connect(self._refresh_cards)
        self._card_refresh_button = QPushButton(self._translator.t("common.refresh"))
        self._card_refresh_button.clicked.connect(self._refresh_cards)
        search_row.addWidget(self._card_search)
        search_row.addWidget(self._card_refresh_button)
        layout.addLayout(search_row)

        self._cards_table = QTableWidget(0, 5)
        self._cards_table.setHorizontalHeaderLabels(
            [
                self._translator.t("browse.cards.name"),
                self._translator.t("browse.cards.type"),
                self._translator.t("browse.cards.cmc"),
                self._translator.t("browse.cards.copies"),
                self._translator.t("browse.cards.flags"),
            ]
        )
        self._cards_table.horizontalHeader().setStretchLastSection(True)
        self._cards_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self._cards_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._cards_table.itemSelectionChanged.connect(self._on_card_selected)

        self._card_preview = CardPreviewPanel(self._translator)
        self._card_preview.setVisible(self._show_card_images)

        self._cards_splitter = build_preview_splitter(
            self._cards_table, self._card_preview
        )
        layout.addWidget(self._cards_splitter)
        return panel

    def _on_card_selected(self) -> None:
        item = self._cards_table.currentItem()
        row = item.row() if item is not None else -1
        name_item = self._cards_table.item(row, 0) if row >= 0 else None
        if name_item is None:
            self._card_preview.clear()
            return
        oracle_id = name_item.data(CARD_ORACLE_ID_ROLE)
        if not isinstance(oracle_id, str):
            self._card_preview.clear()
            return
        self._card_preview.set_card(oracle_id, name_item.text())

    def _build_inventory_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        self._inventory_summary_group = QGroupBox(
            self._translator.t("inventory.summary.title")
        )
        summary_layout = QVBoxLayout(self._inventory_summary_group)
        self._inventory_summary_label = QLabel()
        self._inventory_summary_label.setWordWrap(True)
        summary_layout.addWidget(self._inventory_summary_label)
        layout.addWidget(self._inventory_summary_group)

        self._inventory_search = QLineEdit()
        self._inventory_search.setPlaceholderText(
            self._translator.t("inventory.search.name")
        )
        self._inventory_search.textChanged.connect(self._refresh_inventory)
        layout.addWidget(self._inventory_search)

        self._inventory_status = QLabel("")
        self._inventory_status.setWordWrap(True)
        layout.addWidget(self._inventory_status)

        self._inventory_hint = QLabel(self._translator.t("inventory.search.hint"))
        self._inventory_hint.setWordWrap(True)
        layout.addWidget(self._inventory_hint)

        self._inventory_results_table = QTableWidget(0, 5)
        self._inventory_results_table.setHorizontalHeaderLabels(
            [
                self._translator.t("browse.cards.name"),
                self._translator.t("inventory.table.total"),
                self._translator.t("inventory.table.free"),
                self._translator.t("inventory.table.assigned"),
                self._translator.t("inventory.table.decks"),
            ]
        )
        header = self._inventory_results_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(INV_COL_NAME, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(INV_COL_TOTAL, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(INV_COL_FREE, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(
            INV_COL_ASSIGNED, QHeaderView.ResizeMode.ResizeToContents
        )
        header.setSectionResizeMode(INV_COL_DECKS, QHeaderView.ResizeMode.Interactive)
        header.resizeSection(INV_COL_DECKS, 220)
        layout.addWidget(self._inventory_results_table)
        return panel

    def _build_history_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        filter_row = QHBoxLayout()
        self._history_filter_label = QLabel(
            self._translator.t("browse.history.filter")
        )
        self._history_filter = QComboBox()
        configure_data_combo(self._history_filter)
        self._history_filter.currentIndexChanged.connect(self._refresh_history)
        filter_row.addWidget(self._history_filter_label)
        filter_row.addWidget(self._history_filter, stretch=1)
        layout.addLayout(filter_row)
        self._sync_history_filter_combo()

        actions = QHBoxLayout()
        self._history_undo = QPushButton(self._translator.t("browse.history.undo"))
        self._history_undo.clicked.connect(self._undo_last_history)
        actions.addWidget(self._history_undo)
        self._history_redo = QPushButton(self._translator.t("browse.history.redo"))
        self._history_redo.clicked.connect(self._redo_last_history)
        actions.addWidget(self._history_redo)
        self._history_export = QPushButton(
            self._translator.t("browse.history.export")
        )
        self._history_export.clicked.connect(self._export_history)
        actions.addWidget(self._history_export)
        actions.addStretch()
        layout.addLayout(actions)

        self._history_empty = QLabel(self._translator.t("browse.history.empty"))
        self._history_empty.setWordWrap(True)
        layout.addWidget(self._history_empty)

        self._history_table = QTableWidget(0, 2)
        self._history_table.setHorizontalHeaderLabels(
            [
                self._translator.t("browse.history.when"),
                self._translator.t("browse.history.event"),
            ]
        )
        self._history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._history_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self._history_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._history_table.verticalHeader().setVisible(False)
        history_header = self._history_table.horizontalHeader()
        history_header.setStretchLastSection(True)
        history_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        history_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self._history_table, stretch=1)

        self._history_load_more = QPushButton(
            self._translator.t("browse.history.load_more")
        )
        self._history_load_more.clicked.connect(self._load_more_history)
        layout.addWidget(self._history_load_more)
        self._history_oldest_id: int | None = None
        self._history_has_more = False
        return panel

    def _sync_history_filter_combo(self) -> None:
        current = self._history_filter.currentData()
        self._history_filter.blockSignals(True)
        self._history_filter.clear()
        self._history_filter.addItem(
            self._translator.t("browse.history.filter.all"), None
        )
        self._history_filter.addItem(
            self._translator.t("browse.history.filter.inventory"),
            ActivityCategory.INVENTORY.value,
        )
        self._history_filter.addItem(
            self._translator.t("browse.history.filter.decks"),
            ActivityCategory.DECKS.value,
        )
        if current is not None:
            index = self._history_filter.findData(current)
            if index >= 0:
                self._history_filter.setCurrentIndex(index)
        self._history_filter.blockSignals(False)

    def _format_history_event(self, summary_key: str, payload: dict) -> str:
        values = dict(payload)
        if summary_key == "history.event.plan_applied":
            donors = payload.get("donor_names") or []
            if donors:
                values["donors_suffix"] = self._translator.t(
                    "history.event.plan_applied.donors"
                ).format(donors=", ".join(str(name) for name in donors))
            else:
                values["donors_suffix"] = ""
        if summary_key == "history.event.undone":
            undone_type = payload.get("undone_event_type", "")
            values.setdefault("detail", undone_type)
            name = payload.get("deck_name") or payload.get("name")
            if name:
                values["detail"] = str(name)
        try:
            return self._translator.t(summary_key).format(**values)
        except (KeyError, ValueError):
            return self._translator.t(summary_key)

    def _history_category(self) -> ActivityCategory | None:
        category_value = self._history_filter.currentData()
        if category_value == ActivityCategory.INVENTORY.value:
            return ActivityCategory.INVENTORY
        if category_value == ActivityCategory.DECKS.value:
            return ActivityCategory.DECKS
        return None

    def _append_history_rows(self, rows: list[ActivityEventRow]) -> None:
        start = self._history_table.rowCount()
        self._history_table.setRowCount(start + len(rows))
        for offset, row in enumerate(rows):
            row_index = start + offset
            created = row.created_at
            if created.tzinfo is not None:
                local_dt = created.astimezone()
            else:
                local_dt = created
            when = local_dt.strftime("%Y-%m-%d %H:%M")
            event_text = self._format_history_event(row.summary_key, row.payload)
            when_item = QTableWidgetItem(when)
            when_item.setFlags(when_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            event_item = QTableWidgetItem(event_text)
            event_item.setFlags(event_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._history_table.setItem(row_index, 0, when_item)
            self._history_table.setItem(row_index, 1, event_item)
        if rows:
            self._history_oldest_id = rows[-1].id

    def _update_history_undo_redo_enabled(self) -> None:
        with get_session() as session:
            activity = ActivityService(session)
            can_undo = activity.can_undo_last()
            can_redo = activity.can_redo_last()
        self._history_undo.setEnabled(can_undo)
        self._history_redo.setEnabled(can_redo)

    def _load_more_history(self) -> None:
        if not self._history_has_more or self._history_oldest_id is None:
            return
        category = self._history_category()
        with get_session() as session:
            rows = ActivityService(session).list_events(
                category=category,
                limit=HISTORY_PAGE_SIZE,
                before_id=self._history_oldest_id,
            )
        self._history_has_more = len(rows) >= HISTORY_PAGE_SIZE
        self._history_load_more.setVisible(self._history_has_more)
        self._append_history_rows(rows)

    def _export_history(self) -> None:
        path, _selected = QFileDialog.getSaveFileName(
            self,
            self._translator.t("browse.history.export"),
            "mtg-rebuilder-history.csv",
            "CSV (*.csv)",
        )
        if not path:
            return
        category = self._history_category()
        try:
            with get_session() as session:
                csv_text = ActivityService(session).events_csv(category=category)
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write(csv_text)
        except Exception as exc:
            QMessageBox.critical(
                self,
                self._translator.t("common.error"),
                str(exc),
            )

    def _undo_last_history(self) -> None:
        answer = QMessageBox.question(
            self,
            self._translator.t("browse.history.undo"),
            self._translator.t("browse.history.undo.confirm"),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            with get_session() as session:
                ActivityService(session).undo_last()
        except Exception as exc:
            QMessageBox.critical(
                self,
                self._translator.t("common.error"),
                str(exc),
            )
            return
        self._refresh_history()
        self.changed.emit()

    def _redo_last_history(self) -> None:
        answer = QMessageBox.question(
            self,
            self._translator.t("browse.history.redo"),
            self._translator.t("browse.history.redo.confirm"),
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            with get_session() as session:
                ActivityService(session).redo_last()
        except Exception as exc:
            QMessageBox.critical(
                self,
                self._translator.t("common.error"),
                str(exc),
            )
            return
        self._refresh_history()
        self.changed.emit()

    def _build_scryfall_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        self._scryfall_group = QGroupBox(self._translator.t("browse.section.scryfall"))
        form = QFormLayout(self._scryfall_group)
        self._scryfall_status_label = QLabel()
        self._scryfall_status_label.setWordWrap(True)
        form.addRow(self._scryfall_status_label)

        self._sync_progress_label = QLabel("")
        self._sync_progress_label.setWordWrap(True)
        form.addRow(self._sync_progress_label)

        self._sync_button = QPushButton()
        self._sync_button.clicked.connect(self._start_oracle_sync)
        form.addRow(self._sync_button)

        self._unique_button = QPushButton(
            self._translator.t("browse.scryfall.sync_unique")
        )
        self._unique_button.clicked.connect(self._start_unique_sync)
        form.addRow(self._unique_button)

        self._images_collection_button = QPushButton(
            self._translator.t("browse.scryfall.images_collection")
        )
        self._images_collection_button.clicked.connect(
            self._start_images_collection
        )
        form.addRow(self._images_collection_button)

        self._images_cached_button = QPushButton(
            self._translator.t("browse.scryfall.images_cached")
        )
        self._images_cached_button.clicked.connect(self._start_images_cached)
        form.addRow(self._images_cached_button)

        self._card_data_button = QPushButton(
            self._translator.t("browse.scryfall.card_data_refresh")
        )
        self._card_data_button.clicked.connect(self._start_card_data_refresh)
        form.addRow(self._card_data_button)
        layout.addWidget(self._scryfall_group)

        self._scryfall_info = QLabel(self._translator.t("browse.scryfall.info"))
        self._scryfall_info.setWordWrap(True)
        layout.addWidget(self._scryfall_info)
        layout.addStretch()
        self._update_oracle_button_label()
        return panel

    def refresh(self) -> None:
        self._refresh_overview()
        self._refresh_cards()
        self._availability_dirty = True
        if self._section_list.currentRow() == AVAILABILITY_SECTION_INDEX:
            self._refresh_inventory()
        self._refresh_history()
        self._refresh_scryfall_status()
        if self._section_list.currentRow() == SCRYFALL_SECTION_INDEX:
            self._start_remote_status_check()

    def refresh_collection_stats(self) -> None:
        """Update overview + availability + history after deck/inventory changes.

        Skips rebuilding the full Scryfall cards table (tens of thousands of rows).
        Availability is rebuilt only when that Browse section is visible.
        """
        self._refresh_overview()
        self._availability_dirty = True
        if self._section_list.currentRow() == AVAILABILITY_SECTION_INDEX:
            self._refresh_inventory()
        self._refresh_history()
        if self._card_search.text().strip():
            self._refresh_cards()

    def _refresh_history(self) -> None:
        category = self._history_category()
        with get_session() as session:
            rows = ActivityService(session).list_events(
                category=category,
                limit=HISTORY_PAGE_SIZE,
            )

        self._history_table.setRowCount(0)
        self._history_oldest_id = None
        self._history_has_more = len(rows) >= HISTORY_PAGE_SIZE
        self._history_load_more.setVisible(self._history_has_more)
        self._append_history_rows(rows)
        self._history_empty.setVisible(self._history_table.rowCount() == 0)
        self._history_table.setVisible(self._history_table.rowCount() > 0)
        self._update_history_undo_redo_enabled()

    def _refresh_overview(self) -> None:
        self._greeting_label.setText(self._translator.t("browse.overview.greeting"))
        self._tagline_label.setText(self._translator.t("browse.overview.tagline"))
        with get_session() as session:
            stats = BrowseService(session).overview()
        self._overview_label.setText(
            self._translator.t("browse.overview.body").format(
                cards=stats.cards,
                copies=stats.copies,
                unassigned=stats.unassigned_copies,
                decks=stats.decks,
                armed=stats.armed_decks,
                deck_cards=stats.deck_cards,
                assignments=stats.assignments,
            )
        )

    def _refresh_cards(self) -> None:
        search = self._card_search.text().strip()
        if not search:
            # Avoid loading the full ~36k oracle-cards cache into the table.
            self._cards_table.setRowCount(0)
            self._card_preview.clear()
            return

        with get_session() as session:
            cards = BrowseService(session).list_cards(search)

        self._cards_table.setRowCount(len(cards))
        self._card_preview.clear()
        for row, card in enumerate(cards):
            flags: list[str] = []
            if card.is_basic_land:
                flags.append(self._translator.t("browse.cards.flag.basic"))
            if card.is_token:
                flags.append(self._translator.t("browse.cards.flag.token"))
            name_item = QTableWidgetItem(card.name)
            name_item.setData(CARD_ORACLE_ID_ROLE, card.oracle_id)
            self._cards_table.setItem(row, 0, name_item)
            self._cards_table.setItem(row, 1, QTableWidgetItem(card.type_line or ""))
            self._cards_table.setItem(
                row, 2, QTableWidgetItem("" if card.cmc is None else str(card.cmc))
            )
            self._cards_table.setItem(row, 3, QTableWidgetItem(str(card.copy_count)))
            self._cards_table.setItem(row, 4, QTableWidgetItem(", ".join(flags)))

    def _refresh_inventory(self) -> None:
        self._availability_dirty = False
        with get_session() as session:
            all_rows = BrowseService(session).list_inventory()

        if not all_rows:
            self._inventory_summary_label.setText(
                self._translator.t("inventory.summary.empty")
            )
        else:
            total_copies = sum(row.total_copies for row in all_rows)
            free_copies = sum(row.free_copies for row in all_rows)
            assigned_copies = total_copies - free_copies
            self._inventory_summary_label.setText(
                self._translator.t("inventory.summary.body").format(
                    unique=len(all_rows),
                    copies=total_copies,
                    free=free_copies,
                    assigned=assigned_copies,
                )
            )

        search = self._inventory_search.text().strip()
        rows = all_rows
        if search:
            needle = search.casefold()
            rows = [row for row in rows if needle in row.card_name.casefold()]

        self._inventory_results_table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            assigned = row.total_copies - row.free_copies
            decks_text = format_inventory_decks(row, self._translator)

            total_item = QTableWidgetItem(str(row.total_copies))
            total_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            free_item = QTableWidgetItem(str(row.free_copies))
            free_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            assigned_item = QTableWidgetItem(str(assigned))
            assigned_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            decks_item = QTableWidgetItem(decks_text)
            if row.assigned_decks:
                decks_item.setToolTip("\n".join(row.assigned_decks))

            self._inventory_results_table.setItem(
                index, INV_COL_NAME, QTableWidgetItem(row.card_name)
            )
            self._inventory_results_table.setItem(index, INV_COL_TOTAL, total_item)
            self._inventory_results_table.setItem(index, INV_COL_FREE, free_item)
            self._inventory_results_table.setItem(
                index, INV_COL_ASSIGNED, assigned_item
            )
            self._inventory_results_table.setItem(index, INV_COL_DECKS, decks_item)

        if not search:
            self._inventory_status.setText("")
            self._inventory_hint.setVisible(True)
            self._inventory_results_table.setVisible(False)
            return

        self._inventory_hint.setVisible(False)
        self._inventory_results_table.setVisible(True)

        if not rows:
            self._inventory_status.setText(self._translator.t("inventory.not_owned"))
            return

        if len(rows) == 1:
            self._inventory_status.setText(
                format_availability_status(rows[0], self._translator)
            )
            return

        self._inventory_status.setText(
            self._translator.t("inventory.matches").format(count=len(rows))
        )

    def _refresh_scryfall_status(self) -> None:
        """Rebuild the Scryfall panel's status; deferred while that panel is hidden."""
        if self._section_list.currentRow() != SCRYFALL_SECTION_INDEX:
            self._scryfall_status_dirty = True
            return
        self._scryfall_status_dirty = False
        with get_session() as session:
            status = BrowseService(session).scryfall_status()
            images = CardImageService(session).status()

        if self._bulk_status is not None and self._bulk_status.remote_updated_at:
            status = BulkSyncStatus(
                cached_cards=status.cached_cards,
                pack_type=status.pack_type,
                bulk_updated_at=status.bulk_updated_at,
                last_synced_at=status.last_synced_at,
                imported_cards=status.imported_cards,
                remote_updated_at=self._bulk_status.remote_updated_at,
                update_available=(
                    self._bulk_status.remote_updated_at is not None
                    and (
                        status.bulk_updated_at is None
                        or self._bulk_status.remote_updated_at > status.bulk_updated_at
                    )
                ),
            )
        self._bulk_status = status
        self._apply_scryfall_status(status, images)

    def _apply_scryfall_status(
        self, status: BulkSyncStatus, images: ImageCacheStatus
    ) -> None:
        never = self._translator.t("browse.scryfall.never")
        imported = (
            str(status.imported_cards)
            if status.imported_cards is not None
            else never
        )
        if status.remote_updated_at is None and status.last_synced_at is not None:
            update_text = self._translator.t("browse.scryfall.update_unknown")
        elif status.update_available:
            update_text = self._translator.t("browse.scryfall.update_yes")
        else:
            update_text = self._translator.t("browse.scryfall.update_no")

        self._scryfall_status_label.setText(
            self._translator.t("browse.scryfall.status").format(
                cached=status.cached_cards,
                pack=status.pack_type
                or self._translator.t("browse.scryfall.none"),
                bulk_updated=status.bulk_updated_at or never,
                last_synced=status.last_synced_at or never,
                imported=imported,
                update_available=update_text,
                images_collection=(
                    f"{images.collection_on_disk:,}/{images.collection_with_uri:,}"
                ),
                images_cached=f"{images.cached_on_disk:,}/{images.cached_with_uri:,}",
            )
        )
        self._update_oracle_button_label()
        self._set_scryfall_busy(self._scryfall_busy)

    def _update_oracle_button_label(self) -> None:
        status = self._bulk_status
        if status is None or status.cached_cards == 0 or status.last_synced_at is None:
            self._sync_button.setText(
                self._translator.t("browse.scryfall.sync_download")
            )
            self._sync_button.setProperty("oracle_action", "download")
            return
        if status.pack_type == SCRYFALL_BULK_ORACLE_TYPE and not status.update_available:
            self._sync_button.setText(
                self._translator.t("browse.scryfall.sync_current")
            )
            self._sync_button.setProperty("oracle_action", "current")
            return
        if status.pack_type == SCRYFALL_BULK_ORACLE_TYPE and status.update_available:
            self._sync_button.setText(
                self._translator.t("browse.scryfall.sync_update")
            )
            self._sync_button.setProperty("oracle_action", "update")
            return
        self._sync_button.setText(self._translator.t("browse.scryfall.sync_resync"))
        self._sync_button.setProperty("oracle_action", "resync")

    def _any_scryfall_worker_running(self) -> bool:
        for worker in (
            self._sync_worker,
            self._card_data_worker,
            self._image_worker,
        ):
            if worker is not None and worker.isRunning():
                return True
        return False

    def _set_scryfall_busy(self, busy: bool) -> None:
        self._scryfall_busy = busy
        status = self._bulk_status
        oracle_current = (
            status is not None
            and status.pack_type == SCRYFALL_BULK_ORACLE_TYPE
            and not status.update_available
            and status.cached_cards > 0
            and status.last_synced_at is not None
        )
        self._sync_button.setEnabled(not busy and not oracle_current)
        self._unique_button.setEnabled(not busy)
        self._images_collection_button.setEnabled(not busy)
        self._images_cached_button.setEnabled(not busy)
        self._card_data_button.setEnabled(not busy)

    def _start_remote_status_check(self) -> None:
        if self._scryfall_busy:
            return
        if self._remote_worker is not None and self._remote_worker.isRunning():
            return

        self._remote_worker = RemoteBulkStatusWorker()
        self._remote_worker.finished_ok.connect(self._on_remote_status)
        self._remote_worker.failed.connect(self._on_remote_status_failed)
        self._remote_worker.start()

    def _on_remote_status(self, status: object) -> None:
        if not isinstance(status, BulkSyncStatus):
            return
        self._bulk_status = status
        with get_session() as session:
            images = CardImageService(session).status()
        self._apply_scryfall_status(status, images)

    def _on_remote_status_failed(self, _message: str) -> None:
        # Keep local status; update_available stays unknown.
        self._refresh_scryfall_status()

    def _start_oracle_sync(self) -> None:
        self._start_bulk_sync(SCRYFALL_BULK_ORACLE_TYPE)

    def _start_unique_sync(self) -> None:
        reply = QMessageBox.question(
            self,
            self._translator.t("browse.scryfall.confirm_unique_title"),
            self._translator.t("browse.scryfall.confirm_unique_body"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._start_bulk_sync(SCRYFALL_BULK_UNIQUE_ARTWORK_TYPE)

    def _start_bulk_sync(self, pack_type: str) -> None:
        if self._any_scryfall_worker_running():
            return

        self._set_scryfall_busy(True)
        self._sync_progress_label.setText(self._translator.t("browse.scryfall.starting"))

        self._sync_worker = BulkSyncWorker(pack_type)
        self._sync_worker.progress.connect(self._sync_progress_label.setText)
        self._sync_worker.finished_ok.connect(self._on_sync_finished)
        self._sync_worker.failed.connect(self._on_sync_failed)
        self._sync_worker.start()

    def _on_sync_finished(self, imported_cards: int, pack_type: str) -> None:
        self._set_scryfall_busy(False)
        self._sync_progress_label.setText(
            self._translator.t("browse.scryfall.done").format(
                count=imported_cards, pack=pack_type
            )
        )
        self._bulk_status = None
        # Status + overview only here; Inventory/Decks/Optimize reload when shown.
        self._refresh_scryfall_status()
        self._refresh_overview()
        self._availability_dirty = True
        if self._card_search.text().strip():
            self._refresh_cards()
        self.changed.emit()

    def _on_sync_failed(self, message: str) -> None:
        self._set_scryfall_busy(False)
        self._sync_progress_label.setText("")
        QMessageBox.critical(
            self,
            self._translator.t("common.error"),
            format_scryfall_job_error(self._translator, message, kind="sync"),
        )

    def _start_images_collection(self) -> None:
        self._start_image_download(ImageDownloadScope.COLLECTION)

    def _start_images_cached(self) -> None:
        reply = QMessageBox.question(
            self,
            self._translator.t("browse.scryfall.confirm_images_title"),
            self._translator.t("browse.scryfall.confirm_images_body"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._start_image_download(ImageDownloadScope.CACHED)

    def _start_image_download(self, scope: ImageDownloadScope) -> None:
        if self._any_scryfall_worker_running():
            return

        self._set_scryfall_busy(True)
        self._sync_progress_label.setText(
            self._translator.t("browse.scryfall.images_starting")
        )
        self._image_worker = ImageDownloadWorker(scope)
        self._image_worker.progress.connect(self._sync_progress_label.setText)
        self._image_worker.finished_ok.connect(self._on_images_finished)
        self._image_worker.failed.connect(self._on_images_failed)
        self._image_worker.start()

    def _on_images_finished(self, downloaded: int, skipped: int) -> None:
        self._set_scryfall_busy(False)
        self._sync_progress_label.setText(
            self._translator.t("browse.scryfall.images_done").format(
                downloaded=downloaded, skipped=skipped
            )
        )
        self._refresh_scryfall_status()

    def _on_images_failed(self, message: str) -> None:
        self._set_scryfall_busy(False)
        self._sync_progress_label.setText("")
        QMessageBox.critical(
            self,
            self._translator.t("common.error"),
            format_scryfall_job_error(self._translator, message, kind="images"),
        )

    def _start_card_data_refresh(self) -> None:
        if self._any_scryfall_worker_running():
            return

        self._set_scryfall_busy(True)
        self._sync_progress_label.setText(
            self._translator.t("browse.scryfall.card_data_starting")
        )

        self._card_data_worker = CardDataRefreshWorker()
        self._card_data_worker.progress.connect(self._sync_progress_label.setText)
        self._card_data_worker.finished_ok.connect(self._on_card_data_finished)
        self._card_data_worker.failed.connect(self._on_card_data_failed)
        self._card_data_worker.start()

    def _on_card_data_finished(self, count: int) -> None:
        self._set_scryfall_busy(False)
        self._sync_progress_label.setText(
            self._translator.t("browse.scryfall.card_data_done").format(count=count)
        )
        # Legalities / rarity / image URLs changed — mark other tabs dirty via
        # changed; avoid a full Browse refresh (history/overview unchanged).
        self._refresh_scryfall_status()
        self._availability_dirty = True
        self.changed.emit()

    def _on_card_data_failed(self, message: str) -> None:
        self._set_scryfall_busy(False)
        self._sync_progress_label.setText("")
        QMessageBox.critical(
            self,
            self._translator.t("common.error"),
            format_scryfall_job_error(self._translator, message, kind="card_data"),
        )
