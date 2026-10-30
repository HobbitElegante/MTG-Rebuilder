"""Reusable card image preview panel backed by the local image cache."""

from collections import OrderedDict
from itertools import count

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QLabel,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from mtg_rebuilder.database import get_session
from mtg_rebuilder.i18n import Translator
from mtg_rebuilder.services.card_image_service import CardImageService
from mtg_rebuilder.services.settings_service import SettingsService

PREVIEW_MIN_WIDTH = 250
# Scryfall "normal" images are 488x680.
PREVIEW_ASPECT = 680 / 488
_PIXMAP_CACHE_SIZE = 64

_pixmap_cache: OrderedDict[tuple[str, str], QPixmap] = OrderedDict()
_owner_ids = count(1)


def _cached_pixmap(key: tuple[str, str]) -> QPixmap | None:
    pixmap = _pixmap_cache.get(key)
    if pixmap is not None:
        _pixmap_cache.move_to_end(key)
    return pixmap


def _cache_pixmap(key: tuple[str, str], pixmap: QPixmap) -> None:
    _pixmap_cache[key] = pixmap
    _pixmap_cache.move_to_end(key)
    while len(_pixmap_cache) > _PIXMAP_CACHE_SIZE:
        _pixmap_cache.popitem(last=False)


class _ImageWorker(QThread):
    """Resolves one card face off the GUI thread (disk hit or download)."""

    resolved = Signal(str, bool, object, bool, str)

    def __init__(
        self, oracle_id: str, back: bool, printing_id: str | None = None
    ) -> None:
        super().__init__()
        self._oracle_id = oracle_id
        self._back = back
        self._printing_id = printing_id

    def run(self) -> None:
        path = None
        has_back = False
        shown_printing = ""
        try:
            with get_session() as session:
                images = CardImageService(session)
                try:
                    if self._printing_id:
                        path = images.ensure_printing_image(self._printing_id)
                        if path is not None:
                            shown_printing = self._printing_id
                    if path is None:
                        path = images.ensure_image(self._oracle_id, back=self._back)
                        has_back = images.has_back_image(self._oracle_id)
                finally:
                    images.close()
        except Exception:
            path = None

        image = QImage(str(path)) if path is not None else QImage()
        self.resolved.emit(
            self._oracle_id,
            self._back,
            None if image.isNull() else image,
            has_back,
            shown_printing,
        )


class _ImageLoader(QObject):
    """Serializes preview requests so only one Scryfall download runs at a time.

    Requests are keyed by panel, so a newly selected card replaces that panel's
    pending request instead of queueing behind it, while panels shown together
    (commander plus secondary) still each get an image.
    """

    resolved = Signal(str, bool, object, bool, str)

    def __init__(self) -> None:
        super().__init__()
        self._pending: dict[int, tuple[str, bool, str | None]] = {}
        self._active: _ImageWorker | None = None

    def request(
        self,
        owner: int,
        oracle_id: str,
        back: bool,
        printing_id: str | None = None,
    ) -> None:
        self._pending[owner] = (oracle_id, back, printing_id)
        self._start_next()

    def cancel(self, owner: int) -> None:
        self._pending.pop(owner, None)

    def _start_next(self) -> None:
        if self._active is not None or not self._pending:
            return
        owner = next(iter(self._pending))
        oracle_id, back, printing_id = self._pending.pop(owner)
        worker = _ImageWorker(oracle_id, back, printing_id)
        worker.resolved.connect(self.resolved)
        worker.finished.connect(self._on_worker_finished)
        self._active = worker
        worker.start()

    def _on_worker_finished(self) -> None:
        worker = self._active
        self._active = None
        if worker is not None:
            worker.wait()
        self._start_next()


_loader: _ImageLoader | None = None


def image_loader() -> _ImageLoader:
    global _loader
    if _loader is None:
        _loader = _ImageLoader()
    return _loader


class CardPreviewPanel(QWidget):
    """Shows the image of a card, downloading it on demand when missing."""

    def __init__(
        self,
        translator: Translator,
        parent: QWidget | None = None,
        *,
        show_title: bool = True,
    ) -> None:
        super().__init__(parent)
        self._translator = translator
        self._owner = next(_owner_ids)
        self._oracle_id: str | None = None
        self._printing_id: str | None = None
        self._card_name = ""
        self._showing_back = False
        self._has_back = False
        self._pixmap: QPixmap | None = None
        self._show_title = show_title
        self._build_ui()
        image_loader().resolved.connect(self._on_resolved)
        self._render()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._title = QLabel(self._translator.t("preview.title"))
        self._title.setVisible(self._show_title)
        layout.addWidget(self._title)

        self._image = QLabel()
        self._image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image.setWordWrap(True)
        # Ignored size policy keeps the scaled pixmap from driving the layout.
        self._image.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored
        )
        self._image.setMinimumSize(
            PREVIEW_MIN_WIDTH - 30, int((PREVIEW_MIN_WIDTH - 30) * PREVIEW_ASPECT)
        )
        layout.addWidget(self._image, 1)

        self._flip_button = QPushButton(self._translator.t("preview.flip"))
        self._flip_button.clicked.connect(self._toggle_face)
        self._flip_button.setVisible(False)
        layout.addWidget(self._flip_button)

        self.setMinimumWidth(PREVIEW_MIN_WIDTH)

    def retranslate(self) -> None:
        self._title.setText(self._translator.t("preview.title"))
        self._flip_button.setText(self._translator.t("preview.flip"))
        if self._pixmap is None:
            self._render()

    def set_card(
        self,
        oracle_id: str | None,
        name: str = "",
        printing_id: str | None = None,
    ) -> None:
        printing_id = printing_id or None
        if (
            oracle_id == self._oracle_id
            and name == self._card_name
            and printing_id == self._printing_id
        ):
            return
        self._oracle_id = oracle_id or None
        self._printing_id = printing_id
        self._card_name = name
        self._showing_back = False
        self._has_back = False
        self._flip_button.setVisible(False)
        self._pixmap = None
        if self._oracle_id is None:
            image_loader().cancel(self._owner)
        self._render()

    def _cache_key(self) -> tuple[str, str]:
        if self._printing_id:
            return ("printing", self._printing_id)
        return (self._oracle_id or "", "back" if self._showing_back else "front")

    def clear(self) -> None:
        self.set_card(None)

    def _render(self) -> None:
        if self._oracle_id is None:
            self._show_message(self._translator.t("preview.empty"))
            return

        cached = _cached_pixmap(self._cache_key())
        if cached is not None:
            self._pixmap = cached
            self._rescale()
            return

        self._pixmap = None
        self._show_message(self._translator.t("preview.loading"))
        image_loader().request(
            self._owner,
            self._oracle_id,
            False if self._printing_id else self._showing_back,
            self._printing_id,
        )

    def _on_resolved(
        self,
        oracle_id: str,
        back: bool,
        image: object,
        has_back: bool,
        printing_id: str,
    ) -> None:
        if oracle_id != self._oracle_id:
            return
        wanted = self._printing_id or ""
        if printing_id != wanted:
            if not (wanted and printing_id == ""):
                return
            # That printing has no picture. Show the usual card image.
            self._printing_id = None

        key = (
            ("printing", printing_id)
            if printing_id
            else (oracle_id, "back" if back else "front")
        )
        if isinstance(image, QImage):
            _cache_pixmap(key, QPixmap.fromImage(image))

        if not self._printing_id:
            if has_back != self._has_back:
                self._has_back = has_back
                self._flip_button.setVisible(has_back)
            if back != self._showing_back:
                return
        else:
            self._has_back = False
            self._flip_button.setVisible(False)

        cached = _cached_pixmap(self._cache_key())
        if cached is None:
            self._show_message(self._translator.t("preview.missing"))
            return
        self._pixmap = cached
        self._rescale()

    def _toggle_face(self) -> None:
        if self._oracle_id is None or not self._has_back:
            return
        self._showing_back = not self._showing_back
        self._pixmap = None
        self._render()

    def _show_message(self, message: str) -> None:
        self._pixmap = None
        self._image.setPixmap(QPixmap())
        text = f"{self._card_name}\n{message}" if self._card_name else message
        self._image.setText(text)

    def _rescale(self) -> None:
        if self._pixmap is None:
            return
        area = self._image.size()
        if area.width() <= 0 or area.height() <= 0:
            return
        self._image.setText("")
        self._image.setPixmap(
            self._pixmap.scaled(
                area,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().resizeEvent(event)
        self._rescale()


def card_images_enabled() -> bool:
    with get_session() as session:
        return SettingsService(session).get_show_card_images()


def _persist_preview_width(splitter: QSplitter) -> None:
    sizes = splitter.sizes()
    if len(sizes) < 2 or sizes[1] <= 0:
        return
    with get_session() as session:
        SettingsService(session).set_card_preview_width(sizes[1])


def build_preview_splitter(content: QWidget, preview: QWidget) -> QSplitter:
    """Lay a table (or list) beside a preview, remembering the preview width."""
    splitter = QSplitter(Qt.Orientation.Horizontal)
    splitter.addWidget(content)
    splitter.addWidget(preview)
    splitter.setStretchFactor(0, 1)
    splitter.setStretchFactor(1, 0)

    with get_session() as session:
        width = SettingsService(session).get_card_preview_width()
    splitter.setSizes([max(width * 2, 480), width])

    # Dragging emits per pixel, so only write the width once the user settles.
    timer = QTimer(splitter)
    timer.setSingleShot(True)
    timer.setInterval(500)
    timer.timeout.connect(lambda: _persist_preview_width(splitter))
    splitter.splitterMoved.connect(lambda *_: timer.start())
    return splitter
