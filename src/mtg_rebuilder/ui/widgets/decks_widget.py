from pathlib import Path

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QPainter, QShowEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from mtg_rebuilder.database import get_session
from mtg_rebuilder.i18n import Translator
from mtg_rebuilder.models.enums import DeckCardRole, DeckFormat, DeckStatus
from mtg_rebuilder.services import (
    DeckService,
    HouseBanService,
    ImportService,
    ScryfallService,
    SettingsService,
)
from mtg_rebuilder.services.deck_export import load_deck_export_cards
from mtg_rebuilder.services.deck_service import DeckCardSummary
from mtg_rebuilder.services.decklist_parser import DecklistFormat, detect_format
from mtg_rebuilder.ui.error_text import format_deck_url_error
from mtg_rebuilder.ui.combo import configure_data_combo
from mtg_rebuilder.ui.deck_cards_display import (
    COMMAND_GROUP,
    LAND_GROUP,
    OTHER_GROUP,
    DeckCardsSortKey,
    group_deck_cards,
    sort_deck_cards,
)
from mtg_rebuilder.ui.deck_list_display import (
    DeckListRow,
    DeckSortKey,
    coerce_deck_format,
    coerce_deck_status,
    filter_deck_rows,
    sort_deck_rows,
)
from mtg_rebuilder.ui.inventory_display import format_deck_warning_tooltip
from mtg_rebuilder.ui.widgets.card_preview import CardPreviewPanel, PREVIEW_MIN_WIDTH
from mtg_rebuilder.ui.widgets.deck_stats import DeckStatsColumn
from mtg_rebuilder.ui.widgets.import_dialogs import (
    AvailableCopiesDialog,
    CommandZoneFields,
    DECK_FORMAT_I18N,
    DeckDetailsDialog,
    DeckEditDialog,
    DeleteDeckDialog,
    ExportDeckDialog,
    ImportStatusDialog,
    deck_format_from_combo,
    populate_deck_format_combo,
)

DECK_NAME_ROLE = Qt.ItemDataRole.UserRole + 1
DECK_STATUS_ROLE = Qt.ItemDataRole.UserRole + 2
DECK_WARNING_ROLE = Qt.ItemDataRole.UserRole + 3
DECK_LOCKED_ROLE = Qt.ItemDataRole.UserRole + 4
CARD_ORACLE_ROLE = Qt.ItemDataRole.UserRole + 1
CARD_NAME_ROLE = Qt.ItemDataRole.UserRole + 2

_COMMAND_ZONE_ROLES = {
    DeckCardRole.COMMANDER,
    DeckCardRole.PARTNER,
    DeckCardRole.COMPANION,
    DeckCardRole.BACKGROUND,
}
_ROLE_I18N = {
    DeckCardRole.PARTNER: "decks.role.partner",
    DeckCardRole.COMPANION: "decks.role.companion",
    DeckCardRole.BACKGROUND: "decks.role.background",
    DeckCardRole.COMMANDER: "decks.details_edit.commander",
}
_GROUP_I18N = {
    COMMAND_GROUP: "decks.cards.group.command_zone",
    "Creature": "decks.stats.type.creature",
    "Instant": "decks.stats.type.instant",
    "Sorcery": "decks.stats.type.sorcery",
    "Artifact": "decks.stats.type.artifact",
    "Enchantment": "decks.stats.type.enchantment",
    "Planeswalker": "decks.stats.type.planeswalker",
    "Battle": "decks.stats.type.battle",
    LAND_GROUP: "decks.stats.type.land",
    OTHER_GROUP: "decks.cards.group.other",
}
_GROUP_CARD_INDENT = "    "


class DeckListItemDelegate(QStyledItemDelegate):
    """Paint deck name on the left; optional 🔒 / ⚠ then [Armed|Dismantled] right."""

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index,
    ) -> None:
        self.initStyleOption(option, index)
        painter.save()

        style = option.widget.style() if option.widget is not None else None
        if style is not None:
            style.drawPrimitive(
                QStyle.PrimitiveElement.PE_PanelItemViewItem,
                option,
                painter,
                option.widget,
            )

        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        palette = option.palette
        painter.setPen(
            palette.color(
                palette.ColorRole.HighlightedText
                if selected
                else palette.ColorRole.Text
            )
        )
        painter.setFont(option.font)

        name = str(index.data(DECK_NAME_ROLE) or "")
        status = str(index.data(DECK_STATUS_ROLE) or "")
        warning = str(index.data(DECK_WARNING_ROLE) or "")
        locked = str(index.data(DECK_LOCKED_ROLE) or "")
        metrics = option.fontMetrics
        padding = 8
        gap = 6
        status_width = metrics.horizontalAdvance(status)
        warning_width = metrics.horizontalAdvance(warning) if warning else 0
        locked_width = metrics.horizontalAdvance(locked) if locked else 0
        icons_width = 0
        if locked:
            icons_width += locked_width
        if warning:
            icons_width += (gap if icons_width else 0) + warning_width
        trailing = status_width + (gap + icons_width if icons_width else 0) + padding
        rect = option.rect.adjusted(padding, 0, -padding, 0)
        name_rect = QRect(
            rect.left(),
            rect.top(),
            max(0, rect.width() - trailing),
            rect.height(),
        )
        cursor_x = rect.right() - status_width + 1
        status_rect = QRect(
            cursor_x,
            rect.top(),
            status_width,
            rect.height(),
        )
        icon_x = cursor_x
        if warning:
            icon_x -= gap + warning_width
            warn_rect = QRect(
                icon_x,
                rect.top(),
                warning_width,
                rect.height(),
            )
            painter.drawText(
                warn_rect,
                int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight),
                warning,
            )
        if locked:
            icon_x -= gap + locked_width
            lock_rect = QRect(
                icon_x,
                rect.top(),
                locked_width,
                rect.height(),
            )
            painter.drawText(
                lock_rect,
                int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight),
                locked,
            )

        elided = metrics.elidedText(
            name, Qt.TextElideMode.ElideRight, name_rect.width()
        )
        painter.drawText(
            name_rect,
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
            elided,
        )
        painter.drawText(
            status_rect,
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight),
            status,
        )
        painter.restore()


class DecksWidget(QWidget):
    changed = Signal()

    def __init__(self, translator: Translator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._translator = translator
        self._status_filter: DeckStatus | None = None
        self._format_filter: DeckFormat | None = None
        self._sort_key: DeckSortKey = "number"
        self._sort_ascending = True
        self._deck_rows: list[DeckListRow] = []
        # Ephemeral display controls for the deck's card list (like deck sort).
        self._cards_sort_key: DeckCardsSortKey = "alphabetical"
        self._cards_sort_ascending = True
        self._group_cards_by_type = False
        self._deck_card_rows: list[DeckCardSummary] = []
        # Heavy list load waits until Mazos is shown (Browse is the startup tab).
        self._decks_loaded = False
        self._needs_reload = False
        # Deck being re-synced from a paste/URL; None while importing a new deck.
        self._update_deck_id: int | None = None
        self._update_deck_name = ""
        with get_session() as session:
            self._show_card_images = SettingsService(session).get_show_card_images()
        self._build_ui()

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 (Qt override)
        super().showEvent(event)
        if not self._decks_loaded or self._needs_reload:
            self._reload()

    def set_show_card_images(self, enabled: bool) -> None:
        self._show_card_images = enabled
        self._commander_preview.setVisible(enabled)
        self._card_preview.setVisible(enabled)

    def retranslate(self) -> None:
        self._decks_group.setTitle(self._translator.t("decks.list.title"))
        self._show_import_button.setText(self._translator.t("decks.show_import"))
        self._load_file_button.setText(self._translator.t("decks.load_file"))
        self._cancel_import_button.setText(self._translator.t("decks.cancel_import"))
        self._update_list_button.setText(self._translator.t("decks.update_list"))
        self._retranslate_import_panel()
        self._name_input.setPlaceholderText(self._translator.t("decks.name"))
        self._import_text.setPlaceholderText(
            self._translator.t("decks.import.placeholder")
        )
        self._command_zone.retranslate()
        self._edit_details_button.setText(self._translator.t("decks.edit_details"))
        self._edit_button.setText(self._translator.t("decks.edit_list"))
        self._delete_button.setText(self._translator.t("decks.delete_list"))
        self._armed_button.setText(self._translator.t("decks.set_armed"))
        self._dismantled_button.setText(self._translator.t("decks.set_dismantled"))
        self._export_button.setText(self._translator.t("decks.export_list"))
        self._move_up_button.setText(self._translator.t("decks.move_up"))
        self._move_down_button.setText(self._translator.t("decks.move_down"))
        self._lock_button.setText(self._translator.t("decks.lock"))
        self._search.setPlaceholderText(self._translator.t("decks.search"))
        self._format_filter_label.setText(self._translator.t("decks.format"))
        self._filter_label.setText(self._translator.t("decks.filter.label"))
        self._sort_label.setText(self._translator.t("decks.sort.by"))
        self._cards_label.setText(self._translator.t("decks.cards.title"))
        self._cards_filter_label.setText(
            self._translator.t("decks.cards.filter_by")
        )
        self._group_by_type_check.setText(
            self._translator.t("decks.cards.group_by_type")
        )
        self._retranslate_cards_sort()
        self._commander_preview.retranslate()
        self._commander_column.retranslate()
        self._card_preview.retranslate()
        self._retranslate_format_filter()
        self._retranslate_filter()
        self._retranslate_sort()
        if self._decks_loaded:
            self.refresh()

    def _retranslate_import_panel(self) -> None:
        """Import panel doubles as the update panel; labels follow the mode."""
        if self._update_deck_id is None:
            self._import_group.setTitle(self._translator.t("decks.import"))
            self._submit_import_button.setText(
                self._translator.t("decks.submit_import")
            )
            return
        self._import_group.setTitle(
            self._translator.t("decks.update.title").format(
                name=self._update_deck_name
            )
        )
        self._submit_import_button.setText(self._translator.t("decks.update.submit"))

    def _retranslate_format_filter(self) -> None:
        # Only EDH/Commander for now; more formats can join this list later.
        current = self._format_filter_combo.currentData()
        self._format_filter_combo.blockSignals(True)
        self._format_filter_combo.clear()
        self._format_filter_combo.addItem(
            self._translator.t("decks.filter.format.all"), None
        )
        self._format_filter_combo.addItem(
            self._translator.t("decks.format.commander"), DeckFormat.COMMANDER
        )
        index = self._format_filter_combo.findData(current)
        self._format_filter_combo.setCurrentIndex(index if index >= 0 else 0)
        self._format_filter_combo.blockSignals(False)

    def _retranslate_filter(self) -> None:
        current = self._filter_combo.currentData()
        self._filter_combo.blockSignals(True)
        self._filter_combo.clear()
        self._filter_combo.addItem(self._translator.t("decks.filter.all"), None)
        self._filter_combo.addItem(
            self._translator.t("decks.filter.armed"), DeckStatus.ARMED
        )
        self._filter_combo.addItem(
            self._translator.t("decks.filter.dismantled"), DeckStatus.DISMANTLED
        )
        index = self._filter_combo.findData(current)
        self._filter_combo.setCurrentIndex(index if index >= 0 else 0)
        self._filter_combo.blockSignals(False)

    def _retranslate_sort(self) -> None:
        current = self._sort_combo.currentData()
        self._sort_combo.blockSignals(True)
        self._sort_combo.clear()
        self._sort_combo.addItem(self._translator.t("decks.sort.number"), "number")
        self._sort_combo.addItem(self._translator.t("decks.sort.name"), "name")
        self._sort_combo.addItem(self._translator.t("decks.sort.status"), "status")
        index = self._sort_combo.findData(current if current is not None else "number")
        self._sort_combo.setCurrentIndex(index if index >= 0 else 0)
        self._sort_combo.blockSignals(False)
        self._update_sort_dir_button()

    def _update_sort_dir_button(self) -> None:
        key = "decks.sort.asc" if self._sort_ascending else "decks.sort.desc"
        self._sort_dir_button.setText(self._translator.t(key))

    def _retranslate_cards_sort(self) -> None:
        current = self._cards_sort_combo.currentData()
        self._cards_sort_combo.blockSignals(True)
        self._cards_sort_combo.clear()
        self._cards_sort_combo.addItem(
            self._translator.t("decks.cards.sort.mana_value"), "mana_value"
        )
        self._cards_sort_combo.addItem(
            self._translator.t("decks.cards.sort.alphabetical"), "alphabetical"
        )
        index = self._cards_sort_combo.findData(
            current if current is not None else self._cards_sort_key
        )
        self._cards_sort_combo.setCurrentIndex(index if index >= 0 else 0)
        self._cards_sort_combo.blockSignals(False)
        self._update_cards_sort_dir_button()

    def _update_cards_sort_dir_button(self) -> None:
        key = (
            "decks.sort.asc" if self._cards_sort_ascending else "decks.sort.desc"
        )
        self._cards_sort_dir_button.setText(self._translator.t(key))

    def _on_cards_sort_changed(self) -> None:
        data = self._cards_sort_combo.currentData()
        if data in ("mana_value", "alphabetical"):
            self._cards_sort_key = data
        self._render_deck_cards()

    def _toggle_cards_sort_direction(self) -> None:
        self._cards_sort_ascending = not self._cards_sort_ascending
        self._update_cards_sort_dir_button()
        self._render_deck_cards()

    def _on_group_by_type_toggled(self, checked: bool) -> None:
        self._group_cards_by_type = bool(checked)
        self._render_deck_cards()

    def _build_ui(self) -> None:
        self._main_layout = QVBoxLayout(self)

        self._decks_group = QGroupBox(self._translator.t("decks.list.title"))
        decks_layout = QVBoxLayout(self._decks_group)

        filter_row = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText(self._translator.t("decks.search"))
        # textChanged passes the string; do not bind _populate_deck_list directly
        # or that text becomes prefer_deck_id and forces a full detail reload.
        self._search.textChanged.connect(lambda _text: self._populate_deck_list())
        self._format_filter_label = QLabel(self._translator.t("decks.format"))
        self._format_filter_combo = QComboBox()
        configure_data_combo(self._format_filter_combo)
        self._retranslate_format_filter()
        self._format_filter_combo.currentIndexChanged.connect(
            self._on_format_filter_changed
        )
        self._filter_label = QLabel(self._translator.t("decks.filter.label"))
        self._filter_combo = QComboBox()
        configure_data_combo(self._filter_combo)
        self._retranslate_filter()
        self._filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        self._sort_label = QLabel(self._translator.t("decks.sort.by"))
        self._sort_combo = QComboBox()
        configure_data_combo(self._sort_combo)
        self._sort_dir_button = QPushButton()
        self._sort_dir_button.clicked.connect(self._toggle_sort_direction)
        self._retranslate_sort()
        self._sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        self._move_up_button = QPushButton(self._translator.t("decks.move_up"))
        self._move_down_button = QPushButton(self._translator.t("decks.move_down"))
        self._move_up_button.clicked.connect(lambda: self._move_selected(-1))
        self._move_down_button.clicked.connect(lambda: self._move_selected(1))
        filter_row.addWidget(self._search, 1)
        filter_row.addWidget(self._format_filter_label)
        filter_row.addWidget(self._format_filter_combo)
        filter_row.addWidget(self._filter_label)
        filter_row.addWidget(self._filter_combo)
        filter_row.addWidget(self._sort_label)
        filter_row.addWidget(self._sort_combo)
        filter_row.addWidget(self._sort_dir_button)
        filter_row.addWidget(self._move_up_button)
        filter_row.addWidget(self._move_down_button)
        decks_layout.addLayout(filter_row)

        self._deck_list = QListWidget()
        self._deck_list.setItemDelegate(DeckListItemDelegate(self._deck_list))
        self._deck_list.currentItemChanged.connect(self._on_selection_changed)

        self._details = QLabel("")
        self._details.setWordWrap(True)

        list_column = QWidget()
        list_layout = QVBoxLayout(list_column)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.addWidget(self._deck_list, 1)
        list_layout.addWidget(self._details)

        self._commander_preview = CardPreviewPanel(self._translator)
        self._commander_preview.setVisible(self._show_card_images)
        self._commander_column = DeckStatsColumn(
            self._translator, self._commander_preview
        )

        self._cards_label = QLabel(self._translator.t("decks.cards.title"))
        self._deck_cards = QListWidget()
        self._deck_cards.currentItemChanged.connect(self._on_deck_card_selected)
        cards_column = QWidget()
        cards_layout = QVBoxLayout(cards_column)
        cards_layout.setContentsMargins(0, 0, 0, 0)
        cards_layout.addWidget(self._cards_label)
        cards_layout.addWidget(self._deck_cards, 1)

        self._card_preview = CardPreviewPanel(self._translator, show_title=False)
        self._card_preview.setVisible(self._show_card_images)

        # Controls for the card list live above the card preview, separated
        # from the deck filter row by a divider (mirrors the stats column).
        preview_column = QWidget()
        preview_layout = QVBoxLayout(preview_column)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        cards_divider = QFrame()
        cards_divider.setFrameShape(QFrame.Shape.HLine)
        cards_divider.setFrameShadow(QFrame.Shadow.Sunken)
        preview_layout.addWidget(cards_divider)
        cards_controls = QHBoxLayout()
        self._cards_filter_label = QLabel(
            self._translator.t("decks.cards.filter_by")
        )
        self._cards_sort_combo = QComboBox()
        configure_data_combo(self._cards_sort_combo)
        self._cards_sort_dir_button = QPushButton()
        self._cards_sort_dir_button.clicked.connect(
            self._toggle_cards_sort_direction
        )
        self._retranslate_cards_sort()
        self._cards_sort_combo.currentIndexChanged.connect(
            self._on_cards_sort_changed
        )
        cards_controls.addWidget(self._cards_filter_label)
        cards_controls.addWidget(self._cards_sort_combo, 1)
        cards_controls.addWidget(self._cards_sort_dir_button)
        preview_layout.addLayout(cards_controls)
        self._group_by_type_check = QCheckBox(
            self._translator.t("decks.cards.group_by_type")
        )
        self._group_by_type_check.toggled.connect(self._on_group_by_type_toggled)
        preview_layout.addWidget(self._group_by_type_check)
        preview_layout.addWidget(self._card_preview, 1)

        self._detail_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._detail_splitter.addWidget(list_column)
        self._detail_splitter.addWidget(self._commander_column)
        self._detail_splitter.addWidget(cards_column)
        self._detail_splitter.addWidget(preview_column)
        list_column.setMinimumWidth(240)
        cards_column.setMinimumWidth(220)
        self._detail_splitter.setCollapsible(0, False)
        self._detail_splitter.setCollapsible(2, False)
        self._detail_splitter.setStretchFactor(0, 2)
        self._detail_splitter.setStretchFactor(1, 0)
        self._detail_splitter.setStretchFactor(2, 2)
        self._detail_splitter.setStretchFactor(3, 0)
        with get_session() as session:
            preview_width = SettingsService(session).get_card_preview_width()
        preview_width = max(preview_width, PREVIEW_MIN_WIDTH)
        self._detail_splitter.setSizes(
            [320, preview_width, 280, preview_width]
        )
        decks_layout.addWidget(self._detail_splitter, 1)

        self._deck_actions = QWidget()
        actions_layout = QHBoxLayout(self._deck_actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        self._edit_details_button = QPushButton(
            self._translator.t("decks.edit_details")
        )
        self._edit_details_button.clicked.connect(self._edit_selected_details)
        self._edit_button = QPushButton(self._translator.t("decks.edit_list"))
        self._edit_button.clicked.connect(self._edit_selected_deck)
        self._update_list_button = QPushButton(
            self._translator.t("decks.update_list")
        )
        self._update_list_button.clicked.connect(self._update_selected_deck_list)
        self._delete_button = QPushButton(self._translator.t("decks.delete_list"))
        self._delete_button.clicked.connect(self._delete_selected_deck)
        self._armed_button = QPushButton(self._translator.t("decks.set_armed"))
        self._dismantled_button = QPushButton(
            self._translator.t("decks.set_dismantled")
        )
        self._export_button = QPushButton(self._translator.t("decks.export_list"))
        self._lock_button = QPushButton(self._translator.t("decks.lock"))
        self._armed_button.clicked.connect(lambda: self._set_status(DeckStatus.ARMED))
        self._dismantled_button.clicked.connect(
            lambda: self._set_status(DeckStatus.DISMANTLED)
        )
        self._export_button.clicked.connect(self._export_selected_deck)
        self._lock_button.clicked.connect(self._toggle_lock_selected)
        actions_layout.addWidget(self._edit_button)
        actions_layout.addWidget(self._update_list_button)
        actions_layout.addWidget(self._edit_details_button)
        actions_layout.addWidget(self._export_button)
        actions_layout.addWidget(self._delete_button)
        actions_layout.addStretch()
        actions_layout.addWidget(self._lock_button)
        actions_layout.addWidget(self._armed_button)
        actions_layout.addWidget(self._dismantled_button)
        decks_layout.addWidget(self._deck_actions)
        self._deck_actions.setVisible(False)

        # Stretch 1: list fills the tab until the import panel opens.
        self._main_layout.addWidget(self._decks_group, 1)

        trigger_row = QHBoxLayout()
        self._show_import_button = QPushButton(self._translator.t("decks.show_import"))
        self._show_import_button.clicked.connect(self._start_new_import)
        trigger_row.addWidget(self._show_import_button)
        trigger_row.addStretch()
        self._main_layout.addLayout(trigger_row)

        self._import_group = QGroupBox(self._translator.t("decks.import"))
        import_layout = QVBoxLayout(self._import_group)

        form = QFormLayout()
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText(self._translator.t("decks.name"))
        form.addRow(self._name_input)

        self._format_combo = QComboBox()
        configure_data_combo(self._format_combo)
        populate_deck_format_combo(self._format_combo, self._translator)
        form.addRow(self._translator.t("decks.format"), self._format_combo)
        import_layout.addLayout(form)

        self._command_zone = CommandZoneFields(
            self._translator,
            labeled=False,
        )
        import_layout.addWidget(self._command_zone)

        self._import_text = QTextEdit()
        self._import_text.setPlaceholderText(
            self._translator.t("decks.import.placeholder")
        )
        import_layout.addWidget(self._import_text, 1)

        import_buttons = QHBoxLayout()
        self._load_file_button = QPushButton(self._translator.t("decks.load_file"))
        self._load_file_button.clicked.connect(self._load_file)
        self._submit_import_button = QPushButton(
            self._translator.t("decks.submit_import")
        )
        self._submit_import_button.clicked.connect(self._import_text_deck)
        self._cancel_import_button = QPushButton(
            self._translator.t("decks.cancel_import")
        )
        self._cancel_import_button.clicked.connect(self._hide_import_section)
        import_buttons.addWidget(self._load_file_button)
        import_buttons.addWidget(self._submit_import_button)
        import_buttons.addWidget(self._cancel_import_button)
        import_buttons.addStretch()
        import_layout.addLayout(import_buttons)

        self._import_group.setVisible(False)
        # Stretch 0 while hidden; becomes 1 (full tab) when import is open.
        self._main_layout.addWidget(self._import_group, 0)

    @staticmethod
    def _format_label(deck_format: DeckFormat, translator: Translator) -> str:
        for fmt, key in DECK_FORMAT_I18N:
            if fmt is deck_format:
                return translator.t(key)
        return translator.t("decks.format.other")

    @staticmethod
    def _format_deck_label(
        index: int,
        name: str,
        status: DeckStatus,
        deck_format: DeckFormat,
        translator: Translator,
    ) -> tuple[str, str]:
        status_text = (
            translator.t("decks.status.armed")
            if status == DeckStatus.ARMED
            else translator.t("decks.status.dismantled")
        )
        format_text = DecksWidget._format_label(deck_format, translator)
        return f"{index}. {name}", f"[{format_text}] [{status_text}]"

    def _start_new_import(self) -> None:
        self._update_deck_id = None
        self._update_deck_name = ""
        self._name_input.setReadOnly(False)
        self._format_combo.setEnabled(True)
        populate_deck_format_combo(self._format_combo, self._translator)
        self._retranslate_import_panel()
        self._show_import_section()
        self._name_input.setFocus()

    def _show_import_section(self) -> None:
        self._decks_group.setVisible(False)
        self._show_import_button.setVisible(False)
        self._import_group.setVisible(True)
        self._main_layout.setStretchFactor(self._decks_group, 0)
        self._main_layout.setStretchFactor(self._import_group, 1)

    def _hide_import_section(self) -> None:
        self._update_deck_id = None
        self._update_deck_name = ""
        self._name_input.setReadOnly(False)
        self._format_combo.setEnabled(True)
        populate_deck_format_combo(self._format_combo, self._translator)
        self._retranslate_import_panel()
        self._import_group.setVisible(False)
        self._decks_group.setVisible(True)
        self._show_import_button.setVisible(True)
        self._main_layout.setStretchFactor(self._import_group, 0)
        self._main_layout.setStretchFactor(self._decks_group, 1)

    def _on_format_filter_changed(self) -> None:
        # PySide returns StrEnum userData as plain str — coerce, don't isinstance.
        self._format_filter = coerce_deck_format(
            self._format_filter_combo.currentData()
        )
        self._populate_deck_list()

    def _on_filter_changed(self) -> None:
        # PySide returns StrEnum userData as plain str — coerce, don't isinstance.
        self._status_filter = coerce_deck_status(self._filter_combo.currentData())
        self._populate_deck_list()

    def _on_sort_changed(self) -> None:
        data = self._sort_combo.currentData()
        if data in ("number", "name", "status"):
            self._sort_key = data
        self._populate_deck_list()

    def _toggle_sort_direction(self) -> None:
        self._sort_ascending = not self._sort_ascending
        self._update_sort_dir_button()
        self._populate_deck_list()

    def _status_label(self, status: DeckStatus) -> str:
        if status == DeckStatus.ARMED:
            return self._translator.t("decks.status.armed")
        return self._translator.t("decks.status.dismantled")

    def refresh(self) -> None:
        """Reload deck list + warnings. Defers while this tab is hidden."""
        if not self.isVisible():
            self._needs_reload = True
            return
        self._reload()

    def _reload(self) -> None:
        self._decks_loaded = True
        self._needs_reload = False
        selected_id = self._selected_deck_id()
        rows: list[DeckListRow] = []
        with get_session() as session:
            service = DeckService(session)
            settings = SettingsService(session)
            show_legality = settings.get_show_legality_warnings()
            show_rules = settings.get_show_rule_warnings()
            house = HouseBanService(session)
            banned_ids = house.oracle_ids()
            commander_names = service.commander_names_by_deck()
            for deck in service.list_decks():
                legality_issues = (
                    service.commander_legality_issues(deck.id) if show_legality else []
                )
                house_issues = (
                    house.house_ban_issues(deck.id, banned=banned_ids)
                    if banned_ids
                    else []
                )
                issues = legality_issues + house_issues
                rule_issues = (
                    service.commander_rule_issues(deck.id) if show_rules else []
                )
                tip_parts: list[str] = []
                if deck.is_locked:
                    tip_parts.append(self._translator.t("decks.locked.tooltip"))
                has_warning = bool(issues or rule_issues)
                if has_warning:
                    tip_parts.append(
                        format_deck_warning_tooltip(
                            issues, rule_issues, self._translator
                        )
                    )
                rows.append(
                    DeckListRow(
                        id=deck.id,
                        name=deck.name,
                        status=deck.status,
                        sort_order=deck.sort_order,
                        is_locked=deck.is_locked,
                        commander_name=commander_names.get(deck.id),
                        has_warning=has_warning,
                        tooltip="\n\n".join(tip_parts),
                        format=deck.format,
                    )
                )
        self._deck_rows = rows
        self._populate_deck_list(prefer_deck_id=selected_id, reload_detail=True)

    def _populate_deck_list(
        self,
        prefer_deck_id: int | None = None,
        *,
        reload_detail: bool = False,
    ) -> None:
        selected_id = (
            prefer_deck_id
            if isinstance(prefer_deck_id, int)
            else self._selected_deck_id()
        )
        needle = self._search.text()
        visible = filter_deck_rows(
            self._deck_rows,
            status=self._status_filter,
            needle=needle,
            deck_format=self._format_filter,
        )
        visible = sort_deck_rows(
            visible,
            key=self._sort_key,
            ascending=self._sort_ascending,
            status_label=self._status_label,
        )

        self._deck_list.blockSignals(True)
        self._deck_list.clear()
        if not visible:
            empty_key = (
                "decks.empty_filtered"
                if (
                    self._status_filter is not None
                    or self._format_filter is not None
                    or needle.strip()
                )
                else "decks.empty"
            )
            self._deck_list.addItem(self._translator.t(empty_key))
            self._deck_list.blockSignals(False)
            self._deck_actions.setVisible(False)
            self._details.setText("")
            self._clear_deck_detail_panels()
            self._update_move_buttons()
            return

        restore_item: QListWidgetItem | None = None
        for index, deck in enumerate(visible, start=1):
            name_label, status_label = self._format_deck_label(
                index, deck.name, deck.status, deck.format, self._translator
            )
            item = QListWidgetItem(name_label)
            item.setData(Qt.ItemDataRole.UserRole, deck.id)
            item.setData(DECK_NAME_ROLE, name_label)
            item.setData(DECK_STATUS_ROLE, status_label)
            item.setData(
                DECK_LOCKED_ROLE,
                self._translator.t("decks.locked.icon") if deck.is_locked else "",
            )
            item.setData(
                DECK_WARNING_ROLE,
                self._translator.t("decks.legality.warning")
                if deck.has_warning
                else "",
            )
            item.setToolTip(deck.tooltip)
            self._deck_list.addItem(item)
            if deck.id == selected_id:
                restore_item = item

        self._deck_list.blockSignals(False)
        if restore_item is not None:
            self._deck_list.blockSignals(True)
            self._deck_list.setCurrentItem(restore_item)
            self._deck_list.blockSignals(False)
            if reload_detail:
                self._on_selection_changed()
            else:
                self._update_move_buttons()
        elif self._deck_list.count() > 0:
            first = self._deck_list.item(0)
            if first is not None and first.data(Qt.ItemDataRole.UserRole) is not None:
                self._deck_list.setCurrentRow(0)
            else:
                self._update_move_buttons()
        else:
            self._update_move_buttons()

    def _selected_deck_id(self) -> int | None:
        item = self._deck_list.currentItem()
        if item is None:
            return None
        deck_id = item.data(Qt.ItemDataRole.UserRole)
        return deck_id if isinstance(deck_id, int) else None

    def _manual_order_active(self) -> bool:
        return self._sort_key == "number" and self._sort_ascending

    def _update_move_buttons(self) -> None:
        row = self._deck_list.currentRow()
        count = self._deck_list.count()
        has_deck = self._selected_deck_id() is not None
        can_reorder = has_deck and self._manual_order_active()
        self._move_up_button.setEnabled(can_reorder and row > 0)
        self._move_down_button.setEnabled(
            can_reorder and row >= 0 and row < count - 1
        )

    def _update_status_buttons(self, status: DeckStatus) -> None:
        if status == DeckStatus.ARMED:
            self._armed_button.setVisible(False)
            self._dismantled_button.setVisible(True)
            return
        self._armed_button.setVisible(True)
        self._dismantled_button.setVisible(False)

    def _update_lock_button(self, locked: bool) -> None:
        self._lock_button.setText(
            self._translator.t("decks.unlock" if locked else "decks.lock")
        )

    def _toggle_lock_selected(self) -> None:
        deck_id = self._selected_deck_id()
        if deck_id is None:
            return
        with get_session() as session:
            service = DeckService(session)
            deck = service.get_deck(deck_id)
            if deck is None:
                return
            service.set_locked(deck, not deck.is_locked)
        self.refresh()
        self.changed.emit()

    def _clear_deck_detail_panels(self) -> None:
        self._commander_preview.clear()
        self._commander_column.set_stats(None)
        self._card_preview.clear()
        self._deck_card_rows = []
        self._deck_cards.blockSignals(True)
        self._deck_cards.clear()
        self._deck_cards.blockSignals(False)

    def _format_deck_card_label(self, card: DeckCardSummary) -> str:
        if card.role in _COMMAND_ZONE_ROLES:
            role_key = _ROLE_I18N[card.role]
            return self._translator.t("decks.cards.line_role").format(
                qty=card.quantity,
                name=card.name,
                role=self._translator.t(role_key),
            )
        return self._translator.t("decks.cards.line").format(
            qty=card.quantity,
            name=card.name,
        )

    def _load_deck_cards(self, deck_id: int) -> None:
        with get_session() as session:
            service = DeckService(session)
            cards = service.deck_card_summaries(deck_id)
            zone = service.command_zone_cards(deck_id)
            stats = service.deck_statistics(deck_id)

        self._commander_column.set_stats(stats)
        if zone:
            self._commander_preview.set_card(zone[0][0], zone[0][1])
        else:
            self._commander_preview.clear()

        self._deck_card_rows = cards
        self._render_deck_cards(select_oracle=zone[0][0] if zone else None)

    def _make_group_header_item(self, group: str) -> QListWidgetItem:
        item = QListWidgetItem(
            self._translator.t("decks.cards.group_header").format(
                name=self._translator.t(_GROUP_I18N[group])
            )
        )
        # Visible but never selectable: headers carry no card to preview.
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        font = item.font()
        font.setBold(True)
        item.setFont(font)
        return item

    def _make_deck_card_item(
        self, card: DeckCardSummary, *, indented: bool
    ) -> QListWidgetItem:
        label = self._format_deck_card_label(card)
        if indented:
            label = _GROUP_CARD_INDENT + label
        item = QListWidgetItem(label)
        item.setData(CARD_ORACLE_ROLE, card.oracle_id)
        item.setData(CARD_NAME_ROLE, card.name)
        return item

    def _render_deck_cards(self, select_oracle: str | None = None) -> None:
        """Rebuild the card list from cache honoring sort / group controls."""
        if select_oracle is None:
            current = self._deck_cards.currentItem()
            data = current.data(CARD_ORACLE_ROLE) if current is not None else None
            if isinstance(data, str):
                select_oracle = data

        self._deck_cards.blockSignals(True)
        self._deck_cards.clear()
        if not self._deck_card_rows:
            self._deck_cards.addItem(
                QListWidgetItem(self._translator.t("decks.cards.empty"))
            )
            self._deck_cards.blockSignals(False)
            self._card_preview.clear()
            return

        select_row: int | None = None
        first_card_row: int | None = None
        if self._group_cards_by_type:
            groups = group_deck_cards(
                self._deck_card_rows,
                key=self._cards_sort_key,
                ascending=self._cards_sort_ascending,
            )
            for group, cards in groups:
                self._deck_cards.addItem(self._make_group_header_item(group))
                for card in cards:
                    self._deck_cards.addItem(
                        self._make_deck_card_item(card, indented=True)
                    )
                    row = self._deck_cards.count() - 1
                    if first_card_row is None:
                        first_card_row = row
                    if select_oracle and card.oracle_id == select_oracle:
                        select_row = row
        else:
            cards = sort_deck_cards(
                self._deck_card_rows,
                key=self._cards_sort_key,
                ascending=self._cards_sort_ascending,
            )
            for card in cards:
                self._deck_cards.addItem(
                    self._make_deck_card_item(card, indented=False)
                )
                row = self._deck_cards.count() - 1
                if first_card_row is None:
                    first_card_row = row
                if select_oracle and card.oracle_id == select_oracle:
                    select_row = row
        self._deck_cards.blockSignals(False)
        if select_row is None:
            select_row = first_card_row if first_card_row is not None else 0
        self._deck_cards.setCurrentRow(select_row)

    def _on_deck_card_selected(self) -> None:
        item = self._deck_cards.currentItem()
        if item is None:
            self._card_preview.clear()
            return
        oracle_id = item.data(CARD_ORACLE_ROLE)
        name = item.data(CARD_NAME_ROLE)
        if not isinstance(oracle_id, str):
            self._card_preview.clear()
            return
        self._card_preview.set_card(oracle_id, name if isinstance(name, str) else "")

    def _on_selection_changed(self) -> None:
        deck_id = self._selected_deck_id()
        self._update_move_buttons()
        if deck_id is None:
            self._details.setText("")
            self._deck_actions.setVisible(False)
            self._clear_deck_detail_panels()
            return

        self._deck_actions.setVisible(True)
        self._load_deck_cards(deck_id)
        with get_session() as session:
            service = DeckService(session)
            deck = service.get_deck(deck_id)
            if deck is None:
                return
            self._update_status_buttons(deck.status)
            self._update_lock_button(deck.is_locked)
            card_count = sum(card.quantity for card in deck.cards)
            commander = service.commander_name(deck_id)
            secondary = service.secondary_command_zone(deck_id)
            lines: list[str] = [
                self._translator.t("decks.details.format").format(
                    name=self._format_label(deck.format, self._translator)
                )
            ]
            if deck.status == DeckStatus.ARMED:
                lines.append(
                    self._translator.t("decks.details.armed").format(count=card_count)
                )
            else:
                coverage = service.free_coverage_toward_deck(deck_id)
                lines.append(
                    self._translator.t("decks.details.dismantled").format(
                        count=card_count,
                        available=coverage.covered,
                        needed=coverage.required,
                    )
                )
            if commander:
                lines.append(
                    self._translator.t("decks.details.commander").format(name=commander)
                )
            else:
                lines.append(self._translator.t("decks.details.commander_none"))
            if secondary is not None:
                role, name = secondary
                lines.append(
                    self._translator.t("decks.details.secondary").format(
                        role=self._translator.t(_ROLE_I18N[role]),
                        name=name,
                    )
                )
            self._details.setText("\n".join(lines))

    def _move_selected(self, direction: int) -> None:
        if not self._manual_order_active():
            return
        deck_id = self._selected_deck_id()
        if deck_id is None:
            return
        with get_session() as session:
            moved = DeckService(session).move_deck(
                deck_id,
                direction=direction,
                status=self._status_filter,
            )
        if moved:
            # Reorder only — do not emit changed (that refreshes Inventory/Browse).
            self.refresh()

    def _edit_selected_details(self) -> None:
        deck_id = self._selected_deck_id()
        if deck_id is None:
            return

        with get_session() as session:
            service = DeckService(session)
            deck = service.get_deck(deck_id)
            if deck is None:
                return
            deck_name = deck.name
            deck_format = deck.format
            commander = service.commander_name(deck_id)
            secondary = service.secondary_command_zone(deck_id)

        dialog = DeckDetailsDialog(
            self._translator,
            deck_name,
            commander,
            secondary,
            self,
            deck_format=deck_format,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        new_name = dialog.deck_name()
        new_format = dialog.deck_format()
        new_commander = dialog.commander_name()
        secondary_role = dialog.secondary_role()
        secondary_name = dialog.secondary_name()
        try:
            with get_session() as session:
                service = DeckService(session)
                service.rename_deck(deck_id, new_name)
                service.set_format(deck_id, new_format)
                scryfall = ScryfallService(session)
                try:
                    if new_commander is None:
                        service.set_commander(deck_id, None)
                    else:
                        card = scryfall.lookup_local(new_commander)
                        if card is None:
                            raise ValueError(
                                self._translator.t(
                                    "decks.details_edit.commander_not_found"
                                ).format(name=new_commander)
                            )
                        service.set_commander(deck_id, card.oracle_id)

                    if secondary_role is None or secondary_name is None:
                        service.set_secondary_command_zone(deck_id, None, None)
                    else:
                        card = scryfall.lookup_local(secondary_name)
                        if card is None:
                            raise ValueError(
                                self._translator.t(
                                    "decks.details_edit.commander_not_found"
                                ).format(name=secondary_name)
                            )
                        service.set_secondary_command_zone(
                            deck_id, secondary_role, card.oracle_id
                        )
                finally:
                    scryfall.close()
        except Exception as exc:
            QMessageBox.critical(
                self,
                self._translator.t("common.error"),
                str(exc),
            )
            return

        self.refresh()
        self.changed.emit()

    def _export_selected_deck(self) -> None:
        deck_id = self._selected_deck_id()
        if deck_id is None:
            return

        try:
            with get_session() as session:
                deck = DeckService(session).get_deck(deck_id)
                if deck is None:
                    return
                deck_name = deck.name
                cards = load_deck_export_cards(session, deck_id)
        except Exception as exc:
            QMessageBox.critical(
                self,
                self._translator.t("common.error"),
                str(exc),
            )
            return

        ExportDeckDialog(self._translator, deck_name, cards, self).exec()

    def _edit_selected_deck(self) -> None:
        deck_id = self._selected_deck_id()
        if deck_id is None:
            return

        with get_session() as session:
            service = DeckService(session)
            deck = service.get_deck(deck_id)
            if deck is None:
                return
            deck_name = deck.name
            deck_format = deck.format
            rows = service.deck_edit_rows(deck_id)
            house_banned_ids = HouseBanService(session).oracle_ids()
            show_legality = SettingsService(session).get_show_legality_warnings()

        dialog = DeckEditDialog(
            self._translator,
            deck_name,
            rows,
            self,
            house_banned_ids=house_banned_ids,
            show_legality_warnings=show_legality,
            deck_format=deck_format,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            with get_session() as session:
                DeckService(session).apply_deck_edit(
                    deck_id,
                    dialog.edit_lines(),
                    create_free_copies=dialog.create_free_copies(),
                    remove_copies=dialog.remove_copies(),
                )
        except Exception as exc:
            QMessageBox.critical(
                self,
                self._translator.t("common.error"),
                str(exc),
            )
            return

        self.refresh()
        self.changed.emit()

    def _update_selected_deck_list(self) -> None:
        """Open the import panel bound to the selected deck (replace its list)."""
        deck_id = self._selected_deck_id()
        if deck_id is None:
            return

        with get_session() as session:
            service = DeckService(session)
            deck = service.get_deck(deck_id)
            if deck is None:
                return
            deck_name = deck.name
            deck_format = deck.format
            commander = service.commander_name(deck_id)
            secondary = service.secondary_command_zone(deck_id)

        self._update_deck_id = deck_id
        self._update_deck_name = deck_name
        self._name_input.setText(deck_name)
        self._name_input.setReadOnly(True)
        populate_deck_format_combo(
            self._format_combo, self._translator, current=deck_format
        )
        self._format_combo.setEnabled(False)
        self._command_zone.clear()
        self._command_zone.set_commander_name(commander)
        if secondary is not None:
            self._command_zone.set_secondary(secondary[0], secondary[1])
        self._import_text.clear()
        self._retranslate_import_panel()
        self._show_import_section()
        self._import_text.setFocus()

    def _apply_list_update(self, deck_id: int, text: str) -> None:
        secondary_error = self._command_zone.validation_error()
        if secondary_error is not None:
            QMessageBox.warning(
                self,
                self._translator.t("common.error"),
                secondary_error,
            )
            return

        commander = self._command_zone.commander_name()
        secondary_role = self._command_zone.secondary_role()
        secondary_name = self._command_zone.secondary_name()

        try:
            with get_session() as session:
                service = DeckService(session)
                deck = service.get_deck(deck_id)
                if deck is None:
                    return
                deck_name = deck.name
                deck_format = deck.format
                armed = deck.status == DeckStatus.ARMED
                house_banned_ids = HouseBanService(session).oracle_ids()
                show_legality = SettingsService(session).get_show_legality_warnings()
                scryfall = ScryfallService(session)
                try:
                    preview = ImportService(
                        session, scryfall
                    ).preview_deck_list_update(
                        deck_id, text, commander_name=commander
                    )
                finally:
                    scryfall.close()
        except Exception as exc:
            QMessageBox.critical(
                self,
                self._translator.t("common.error"),
                str(exc),
            )
            return

        if not preview.has_changes and not preview.edit_rows:
            QMessageBox.information(
                self,
                self._translator.t("decks.update_list"),
                self._translator.t("decks.update.no_changes"),
            )
            return

        dialog = DeckEditDialog(
            self._translator,
            deck_name,
            preview.edit_rows,
            self,
            house_banned_ids=house_banned_ids,
            show_legality_warnings=show_legality,
            deck_format=deck_format,
            title=self._translator.t("decks.update.title").format(name=deck_name),
            save_label=self._translator.t("decks.update.apply"),
            summary_text=self._translator.t("decks.update.summary").format(
                before=preview.total_before,
                after=preview.total_after,
            ),
            hint_text=self._translator.t("decks.update.copies_hint"),
            armed_warning=(
                self._translator.t("decks.update.armed_warning") if armed else None
            ),
            unresolved_lines=preview.unresolved_lines,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            with get_session() as session:
                service = DeckService(session)
                service.apply_deck_edit(
                    deck_id,
                    dialog.edit_lines(),
                    create_free_copies=dialog.create_free_copies(),
                    remove_copies=dialog.remove_copies(),
                )
                scryfall = ScryfallService(session)
                try:
                    if commander is None:
                        service.set_commander(deck_id, None)
                    else:
                        card = scryfall.lookup_local(commander)
                        if card is None:
                            raise ValueError(
                                self._translator.t(
                                    "decks.details_edit.commander_not_found"
                                ).format(name=commander)
                            )
                        service.set_commander(deck_id, card.oracle_id)
                    if secondary_role is None or secondary_name is None:
                        service.set_secondary_command_zone(deck_id, None, None)
                    else:
                        secondary_card = scryfall.lookup_local(secondary_name)
                        if secondary_card is None:
                            raise ValueError(
                                self._translator.t(
                                    "decks.details_edit.commander_not_found"
                                ).format(name=secondary_name)
                            )
                        service.set_secondary_command_zone(
                            deck_id, secondary_role, secondary_card.oracle_id
                        )
                finally:
                    scryfall.close()
        except Exception as exc:
            QMessageBox.critical(
                self,
                self._translator.t("common.error"),
                str(exc),
            )
            return

        self._name_input.clear()
        self._command_zone.clear()
        self._import_text.clear()
        self._hide_import_section()
        self.refresh()
        self.changed.emit()

    def _delete_selected_deck(self) -> None:
        deck_id = self._selected_deck_id()
        if deck_id is None:
            return

        with get_session() as session:
            service = DeckService(session)
            deck = service.get_deck(deck_id)
            if deck is None:
                return
            deck_name = deck.name
            impacts = service.deck_delete_impact(deck_id)

        dialog = DeleteDeckDialog(self._translator, deck_name, impacts, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        with get_session() as session:
            DeckService(session).delete_deck(deck_id, dialog.removals())

        self.refresh()
        self.changed.emit()

    def _expand_deck_url(self, text: str) -> None:
        """Fetch a Moxfield/Archidekt deck into the form so the user can review it."""
        try:
            with get_session() as session:
                scryfall = ScryfallService(session)
                try:
                    resolved = ImportService(session, scryfall).resolve_decklist_input(
                        text
                    )
                finally:
                    scryfall.close()
        except Exception as exc:
            QMessageBox.critical(
                self,
                self._translator.t("common.error"),
                format_deck_url_error(self._translator, exc),
            )
            return

        self._import_text.setPlainText(resolved.text)
        if resolved.deck_name and not self._name_input.text().strip():
            self._name_input.setText(resolved.deck_name)
        if resolved.commander_name and not self._command_zone.commander_name():
            self._command_zone.set_commander_name(resolved.commander_name)
        if (
            resolved.secondary_role is not None
            and resolved.secondary_name
            and self._command_zone.secondary_role() is None
        ):
            self._command_zone.set_secondary(
                resolved.secondary_role, resolved.secondary_name
            )
        QMessageBox.information(
            self,
            self._translator.t("decks.import"),
            self._translator.t("decks.import.url_filled"),
        )

    def _import_text_deck(self) -> None:
        text = self._import_text.toPlainText().strip()
        if not text:
            return

        # Expand deck URL into the form so the user can review before arming.
        if detect_format(text) in (
            DecklistFormat.MOXFIELD_URL,
            DecklistFormat.ARCHIDEKT_URL,
        ):
            self._expand_deck_url(text)
            return

        if self._update_deck_id is not None:
            self._apply_list_update(self._update_deck_id, text)
            return

        name = self._name_input.text().strip()
        commander = self._command_zone.commander_name()
        secondary_role = self._command_zone.secondary_role()
        secondary_name = self._command_zone.secondary_name()
        if not name:
            return

        secondary_error = self._command_zone.validation_error()
        if secondary_error is not None:
            QMessageBox.warning(
                self,
                self._translator.t("common.error"),
                secondary_error,
            )
            return

        status_dialog = ImportStatusDialog(self._translator, self)
        if status_dialog.exec() != QDialog.DialogCode.Accepted:
            return
        status = status_dialog.selected_status()

        try:
            with get_session() as session:
                scryfall = ScryfallService(session)
                try:
                    secondary_oracle_id: str | None = None
                    if (
                        secondary_role is not None
                        and secondary_name is not None
                    ):
                        secondary_card = scryfall.lookup_local(secondary_name)
                        if secondary_card is None:
                            raise ValueError(
                                self._translator.t(
                                    "decks.details_edit.commander_not_found"
                                ).format(name=secondary_name)
                            )
                        secondary_oracle_id = secondary_card.oracle_id

                    importer = ImportService(session, scryfall)
                    result = importer.import_decklist_text(
                        deck_name=name,
                        text=text,
                        status=status,
                        commander_name=commander,
                        deck_format=deck_format_from_combo(self._format_combo),
                    )
                    deck_service = DeckService(session)
                    if (
                        secondary_role is not None
                        and secondary_oracle_id is not None
                    ):
                        deck_service.set_secondary_command_zone(
                            result.deck.id, secondary_role, secondary_oracle_id
                        )
                    if status == DeckStatus.ARMED:
                        deck_service.set_status(result.deck, DeckStatus.ARMED)
                    deck_id = result.deck.id
                    warnings = list(result.warnings)
                finally:
                    scryfall.close()
        except Exception as exc:
            QMessageBox.critical(
                self,
                self._translator.t("common.error"),
                str(exc),
            )
            return

        if status == DeckStatus.DISMANTLED:
            try:
                with get_session() as session:
                    scryfall = ScryfallService(session)
                    try:
                        trackable = ImportService(
                            session, scryfall
                        ).list_trackable_cards(deck_id)
                    finally:
                        scryfall.close()
            except Exception as exc:
                QMessageBox.critical(
                    self,
                    self._translator.t("common.error"),
                    str(exc),
                )
                return

            if trackable:
                availability = AvailableCopiesDialog(
                    self._translator,
                    trackable,
                    self,
                )
                if availability.exec() == QDialog.DialogCode.Accepted:
                    quantities = availability.quantities()
                    if quantities:
                        try:
                            with get_session() as session:
                                scryfall = ScryfallService(session)
                                try:
                                    ImportService(
                                        session, scryfall
                                    ).apply_available_copies(quantities)
                                finally:
                                    scryfall.close()
                        except Exception as exc:
                            QMessageBox.critical(
                                self,
                                self._translator.t("common.error"),
                                str(exc),
                            )
                            return

        if warnings:
            warning_text = "\n".join(
                f"{warning.line}: {warning.message}" for warning in warnings[:10]
            )
            QMessageBox.warning(
                self,
                self._translator.t("common.error"),
                warning_text,
            )

        self._name_input.clear()
        self._command_zone.clear()
        self._import_text.clear()
        self._hide_import_section()
        self.refresh()
        self.changed.emit()

    def _load_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            self._translator.t("decks.load_file.dialog_title"),
            str(Path.home()),
            "Text files (*.txt *.dek);;MTGO decks (*.dek);;All files (*)",
        )
        if not path:
            return
        content = Path(path).read_text(encoding="utf-8")
        self._import_text.setPlainText(content)
        if self._update_deck_id is None and not self._name_input.text().strip():
            self._name_input.setText(Path(path).stem)

    def _set_status(self, status: DeckStatus) -> None:
        deck_id = self._selected_deck_id()
        if deck_id is None:
            return
        with get_session() as session:
            service = DeckService(session)
            deck = service.get_deck(deck_id)
            if deck is None:
                return
            service.set_status(deck, status)
        self.refresh()
        self.changed.emit()
