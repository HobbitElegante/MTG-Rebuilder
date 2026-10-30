from PySide6.QtCore import QByteArray
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget

from mtg_rebuilder.config import (
    DEFAULT_WINDOW_HEIGHT,
    DEFAULT_WINDOW_WIDTH,
    MIN_WINDOW_HEIGHT,
    MIN_WINDOW_WIDTH,
)
from mtg_rebuilder.database import get_session
from mtg_rebuilder.i18n import Translator
from mtg_rebuilder.services import SettingsService
from mtg_rebuilder.ui.theme import apply_theme
from mtg_rebuilder.ui.widgets.browse_widget import BrowseWidget
from mtg_rebuilder.ui.widgets.decks_widget import DecksWidget
from mtg_rebuilder.ui.widgets.inventory_widget import InventoryWidget
from mtg_rebuilder.ui.widgets.optimizer_widget import OptimizerWidget


class MainWindow(QMainWindow):
    def __init__(self, translator: Translator) -> None:
        super().__init__()
        self._translator = translator
        self.setWindowTitle(self._translator.t("app.title"))
        self.setMinimumSize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)
        self._restore_or_default_geometry()

        self._tabs = QTabWidget()
        self.setCentralWidget(self._tabs)

        self._inventory = InventoryWidget(self._translator)
        self._decks = DecksWidget(self._translator)
        self._optimizer = OptimizerWidget(self._translator)
        self._browse = BrowseWidget(self._translator)

        self._tab_widgets = (
            self._browse,
            self._decks,
            self._inventory,
            self._optimizer,
        )
        self._tab_keys = (
            "tab.browse",
            "tab.decks",
            "tab.inventory",
            "tab.optimize",
        )

        for widget, key in zip(self._tab_widgets, self._tab_keys, strict=True):
            self._tabs.addTab(widget, self._translator.t(key))

        self._inventory.changed.connect(self._on_inventory_changed)
        self._decks.changed.connect(self._on_collection_changed)
        self._optimizer.changed.connect(self._on_optimizer_applied)
        self._browse.changed.connect(self._refresh_from_browse)
        self._browse.locale_changed.connect(self.set_locale)
        self._browse.theme_changed.connect(self.set_theme)
        self._browse.show_images_changed.connect(self._on_show_images_changed)
        self._browse.track_editions_changed.connect(self._on_track_editions_changed)
        self._browse.warning_settings_changed.connect(self._decks.refresh)

    def _restore_or_default_geometry(self) -> None:
        with get_session() as session:
            encoded = SettingsService(session).get_window_geometry()
        if encoded:
            restored = self.restoreGeometry(
                QByteArray.fromBase64(encoded.encode("ascii"))
            )
            if restored:
                return
        self.resize(DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT)

    def closeEvent(self, event: QCloseEvent) -> None:
        encoded = bytes(self.saveGeometry().toBase64()).decode("ascii")
        with get_session() as session:
            SettingsService(session).set_window_geometry(encoded)
        super().closeEvent(event)

    def _on_show_images_changed(self, enabled: bool) -> None:
        self._inventory.set_show_card_images(enabled)
        self._decks.set_show_card_images(enabled)
        self._optimizer.set_show_card_images(enabled)

    def _on_track_editions_changed(self, enabled: bool) -> None:
        self._inventory.set_track_editions(enabled)
        self._decks.set_track_editions(enabled)
        self._optimizer.set_track_editions(enabled)

    def _refresh_from_browse(self) -> None:
        self._inventory.refresh()
        self._decks.refresh()
        self._optimizer.refresh_decks()

    def _on_inventory_changed(self) -> None:
        self._browse.refresh_collection_stats()
        self._optimizer.refresh_decks()

    def _on_collection_changed(self) -> None:
        self._inventory.refresh()
        self._browse.refresh_collection_stats()
        self._optimizer.refresh_decks()

    def _on_optimizer_applied(self) -> None:
        self._decks.refresh()
        self._inventory.refresh()
        self._browse.refresh_collection_stats()
        self._optimizer.refresh_decks()

    def set_locale(self, locale: str) -> None:
        self._translator.set_locale(locale)
        with get_session() as session:
            SettingsService(session).set_ui_locale(locale)
        self.setWindowTitle(self._translator.t("app.title"))
        for index, key in enumerate(self._tab_keys):
            self._tabs.setTabText(index, self._translator.t(key))
        self._browse.retranslate()
        self._decks.retranslate()
        self._inventory.retranslate()
        self._optimizer.retranslate()

    def set_theme(self, theme: str) -> None:
        with get_session() as session:
            SettingsService(session).set_ui_theme(theme)
        app = QApplication.instance()
        if isinstance(app, QApplication):
            apply_theme(app, theme)
