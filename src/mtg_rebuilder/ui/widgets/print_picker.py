"""Visual print grid, in the spirit of Scryfall's "View all prints"."""

from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

import httpx

from mtg_rebuilder.algorithms.copy_traits import normalize_collector_number, normalize_edition
from mtg_rebuilder.config import UNSPECIFIED_EDITION_LABEL
from mtg_rebuilder.database import get_session
from mtg_rebuilder.i18n import Translator
from mtg_rebuilder.services import ScryfallService

_COLUMNS = 5
_THUMB_WIDTH = 120
_THUMB_HEIGHT = 168
_pixmap_cache: dict[str, QPixmap] = {}
# Threads the dialog no longer owns. Qt aborts if a QThread is destroyed
# while it is still running, which happened when a print was chosen before
# every thumbnail had finished downloading.
_running_fetches: list["_ImageFetch"] = []


def format_print_label(set_code: str | None, collector_number: str | None) -> str:
    parts = [part for part in (set_code, collector_number) if part]
    return " ".join(parts) if parts else UNSPECIFIED_EDITION_LABEL


def _retire_fetch(fetcher: "_ImageFetch") -> None:
    try:
        _running_fetches.remove(fetcher)
    except ValueError:
        return
    fetcher.deleteLater()


class _ImageFetch(QThread):
    """Download print thumbnails one at a time. Failures leave the placeholder."""

    ready = Signal(str, bytes)

    def __init__(self, jobs: list[tuple[str, str]]) -> None:
        super().__init__()
        self._jobs = jobs
        self._client: httpx.Client | None = None

    def abort(self) -> None:
        """Stop after the current picture. Closing the client unblocks it."""
        self.requestInterruption()
        client = self._client
        if client is not None:
            try:
                client.close()
            except Exception:
                return

    def run(self) -> None:
        client = httpx.Client(
            timeout=20.0,
            follow_redirects=True,
            headers={"User-Agent": "MTG-Rebuilder/0.10"},
        )
        self._client = client
        try:
            for printing_id, url in self._jobs:
                if self.isInterruptionRequested():
                    return
                if printing_id in _pixmap_cache:
                    continue
                try:
                    response = client.get(url)
                    if response.status_code == 200 and response.content:
                        self.ready.emit(printing_id, response.content)
                except Exception:
                    if self.isInterruptionRequested():
                        return
        finally:
            self._client = None
            try:
                client.close()
            except Exception:
                return


class _PrintTile(QFrame):
    chosen = Signal(str, str, str)

    def __init__(
        self,
        printing_id: str,
        set_code: str,
        collector_number: str | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._printing_id = printing_id
        self._set_code = set_code
        self._collector_number = collector_number
        caption = format_print_label(set_code, collector_number)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedWidth(_THUMB_WIDTH + 16)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        self._image = QLabel(caption)
        self._image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image.setWordWrap(True)
        self._image.setFixedSize(_THUMB_WIDTH, _THUMB_HEIGHT)
        self._image.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(self._image)
        label = QLabel(caption)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(label)
        self._apply_style(False)

    def printing_id(self) -> str:
        return self._printing_id

    def set_selected(self, selected: bool) -> None:
        self._apply_style(selected)

    def show_pixmap(self, pixmap: QPixmap) -> None:
        scaled = pixmap.scaled(
            _THUMB_WIDTH,
            _THUMB_HEIGHT,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._image.setPixmap(scaled)
        self._image.setText("")

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self.chosen.emit(
            self._printing_id,
            self._set_code,
            self._collector_number or "",
        )
        super().mousePressEvent(event)

    def _apply_style(self, selected: bool) -> None:
        border = "2px solid palette(highlight)" if selected else "1px solid palette(mid)"
        self.setStyleSheet(f"QFrame {{ border: {border}; border-radius: 4px; }}")


class PrintPickerDialog(QDialog):
    """Pick one Scryfall printing. The choice carries the set and the number."""

    def __init__(
        self,
        translator: Translator,
        oracle_id: str,
        current_id: str | None,
        parent: QWidget | None = None,
        *,
        current_set: str | None = None,
        current_collector: str | None = None,
    ) -> None:
        super().__init__(parent)
        self._translator = translator
        self._current_id = current_id
        self._printing_id = current_id
        self._set_code = current_set
        self._collector = current_collector
        self._initial_set = current_set
        self._initial_collector = current_collector
        self._cleared = False
        self._tiles: dict[str, _PrintTile] = {}
        self._fetcher: _ImageFetch | None = None
        self._closing = False
        self.setWindowTitle(translator.t("inventory.prints.title"))
        self.resize(860, 640)
        self._build_ui()
        self._load(oracle_id)

    def printing(self) -> tuple[str | None, str | None, str | None]:
        """``(printing_id, set_code, collector_number)`` after the dialog is accepted."""
        if self._cleared:
            return None, None, None
        return self._printing_id, self._set_code, self._collector

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        hint = QLabel(self._translator.t("inventory.prints.hint"))
        hint.setWordWrap(True)
        layout.addWidget(hint)

        none = QPushButton(self._translator.t("inventory.prints.none"))
        none.clicked.connect(self._clear)
        layout.addWidget(none, alignment=Qt.AlignmentFlag.AlignLeft)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._host = QWidget()
        self._grid = QGridLayout(self._host)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        scroll.setWidget(self._host)
        layout.addWidget(scroll, 1)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        typed = QHBoxLayout()
        typed.addWidget(QLabel(self._translator.t("inventory.prints.type")))
        self._set_edit = QLineEdit()
        self._set_edit.setPlaceholderText(self._translator.t("inventory.editions.edition"))
        self._set_edit.setText(self._set_code or "")
        self._number_edit = QLineEdit()
        self._number_edit.setPlaceholderText(
            self._translator.t("inventory.editions.collector")
        )
        self._number_edit.setText(self._collector or "")
        typed.addWidget(self._set_edit, 1)
        typed.addWidget(self._number_edit, 1)
        layout.addLayout(typed)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept_typed)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load(self, oracle_id: str) -> None:
        try:
            with get_session() as session:
                service = ScryfallService(session)
                try:
                    rows = service.list_printings(oracle_id)
                finally:
                    service.close()
        except Exception:
            rows = []
        if not rows:
            self._status.setText(self._translator.t("inventory.prints.empty"))
            return
        jobs: list[tuple[str, str]] = []
        for index, (printing_id, set_code, collector, _label, image_uri) in enumerate(rows):
            tile = _PrintTile(printing_id, set_code, collector)
            tile.chosen.connect(self._choose)
            tile.set_selected(printing_id == self._current_id)
            self._tiles[printing_id] = tile
            cached = _pixmap_cache.get(printing_id)
            if cached is not None:
                tile.show_pixmap(cached)
            elif image_uri:
                jobs.append((printing_id, image_uri))
            row, column = divmod(index, _COLUMNS)
            self._grid.addWidget(tile, row, column)
        if jobs:
            self._fetcher = _ImageFetch(jobs)
            self._fetcher.ready.connect(self._on_image)
            self._fetcher.start()

    def _on_image(self, printing_id: str, payload: bytes) -> None:
        if self._closing:
            return
        pixmap = QPixmap()
        if not pixmap.loadFromData(payload):
            return
        _pixmap_cache[printing_id] = pixmap
        tile = self._tiles.get(printing_id)
        if tile is not None:
            tile.show_pixmap(pixmap)

    def _choose(self, printing_id: str, set_code: str, collector: str) -> None:
        self._cleared = False
        self._printing_id = printing_id
        self._set_code = set_code or None
        self._collector = collector or None
        self.accept()

    def _clear(self) -> None:
        self._cleared = True
        self._printing_id = None
        self._set_code = None
        self._collector = None
        self.accept()

    def _accept_typed(self) -> None:
        """OK uses the typed set and number.

        If those fields are unchanged, the printing already chosen stays.
        Editing them drops the art id, because the typed line is not a picture.
        """
        edition = normalize_edition(self._set_edit.text())
        number = normalize_collector_number(self._number_edit.text())
        if (
            edition is None
            and number is None
            and self._initial_set is None
            and self._initial_collector is None
        ):
            self.reject()
            return
        self._cleared = False
        self._set_code = edition
        self._collector = number
        if edition != self._initial_set or number != self._initial_collector:
            self._printing_id = None
        self.accept()

    def done(self, result: int) -> None:  # noqa: N802 (Qt override)
        self._detach_fetcher()
        super().done(result)

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self._detach_fetcher()
        super().closeEvent(event)

    def _detach_fetcher(self) -> None:
        """Keep the download thread alive until it stops, then delete it.

        Choosing a print closes this dialog at once. Destroying the thread
        with it still inside a download aborts the whole application.
        """
        fetcher = self._fetcher
        if fetcher is None:
            return
        self._fetcher = None
        self._closing = True
        try:
            fetcher.ready.disconnect(self._on_image)
        except (RuntimeError, TypeError):
            pass
        _running_fetches.append(fetcher)
        fetcher.finished.connect(lambda fetcher=fetcher: _retire_fetch(fetcher))
        fetcher.abort()
        if not fetcher.isRunning():
            _retire_fetch(fetcher)
