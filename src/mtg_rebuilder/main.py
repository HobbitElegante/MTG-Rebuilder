import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from mtg_rebuilder.database import get_session, init_db
from mtg_rebuilder.i18n import Translator
from mtg_rebuilder.resources import APP_ICON
from mtg_rebuilder.services import SettingsService
from mtg_rebuilder.ui import MainWindow
from mtg_rebuilder.ui.theme import apply_theme


def main() -> None:
    init_db()
    with get_session() as session:
        settings = SettingsService(session)
        locale = settings.get_ui_locale()
        theme = settings.get_ui_theme()
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(str(APP_ICON)))
    # Wayland ignores the window icon and matches the installed .desktop instead.
    app.setDesktopFileName("mtg-rebuilder")
    apply_theme(app, theme)
    translator = Translator(locale)
    window = MainWindow(translator)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
