"""Scrollable inventory image grid (local cache only; no network downloads).

Uses viewport virtualization: only tiles near the visible scroll window exist as
widgets (viewport + several buffer rows). Scroll sync only mounts/recycles
indices that changed — it does not re-decode or rescale art every pixel. Image
loads are deferred so placeholders paint first. Layout math lives in
``ui.inventory_image_layout`` (Qt-free) for headless tests.
"""

from collections import OrderedDict
from itertools import count
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from mtg_rebuilder.i18n import Translator
from mtg_rebuilder.services.browse_service import InventorySummaryRow
from mtg_rebuilder.ui.inventory_image_layout import (
    CAPTION_EXTRA,
    GRID_COLUMNS,
    THUMB_MIN_WIDTH,
    TILE_PADDING,
    content_height,
    local_front_image_path,
    move_grid_index,
    thumb_height_for_width,
    thumb_width_for_viewport,
    tile_outer_size,
    tile_top_left,
    visible_index_range,
)
from mtg_rebuilder.ui.widgets.card_preview import image_loader

_PIXMAP_CACHE_SIZE = 160

_tile_owner_ids = count(1)

# oracle_id -> QPixmap (hit) or None (ensure failed / unreadable). Disk misses
# that have not been ensured yet are *not* stored, so scroll can still download.
_pixmap_cache: OrderedDict[str, QPixmap | None] = OrderedDict()


def _cached_pixmap(oracle_id: str) -> tuple[bool, QPixmap | None]:
    """Return (known, pixmap). known=False means not yet looked up."""
    if oracle_id not in _pixmap_cache:
        return False, None
    _pixmap_cache.move_to_end(oracle_id)
    return True, _pixmap_cache[oracle_id]


def _store_pixmap(oracle_id: str, pixmap: QPixmap | None) -> None:
    _pixmap_cache[oracle_id] = pixmap
    _pixmap_cache.move_to_end(oracle_id)
    while len(_pixmap_cache) > _PIXMAP_CACHE_SIZE:
        _pixmap_cache.popitem(last=False)


def load_local_pixmap(oracle_id: str, images_dir: Path | None = None) -> QPixmap | None:
    """Return a cached/on-disk pixmap, or None if not available yet.

    Successful loads and permanent failures (after ensure) are cached. A plain
    disk miss is *not* cached so the caller can still request an on-demand
    download when the tile becomes visible.
    """
    known, cached = _cached_pixmap(oracle_id)
    if known:
        return cached
    path = local_front_image_path(oracle_id, images_dir)
    if path is None:
        return None
    pixmap = QPixmap(str(path))
    if pixmap.isNull():
        _store_pixmap(oracle_id, None)
        return None
    _store_pixmap(oracle_id, pixmap)
    return pixmap


def mark_image_unavailable(oracle_id: str) -> None:
    """Remember that ensure_image failed so we do not retry in a tight loop."""
    _store_pixmap(oracle_id, None)


class _CardTile(QFrame):
    clicked = Signal(str)

    def __init__(
        self,
        translator: Translator,
        parent: QWidget | None = None,
        *,
        thumb_width: int = THUMB_MIN_WIDTH,
    ) -> None:
        super().__init__(parent)
        self._translator = translator
        self._owner = next(_tile_owner_ids)
        self._oracle_id = ""
        self._card_name = ""
        self._selected = False
        self._placeholder_loading = True
        self._source_pixmap: QPixmap | None = None
        self._thumb_width = thumb_width
        self._bind_generation = 0
        self.setObjectName("inventoryCardTile")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Keyboard arrows / Enter are handled by InventoryImageGrid.
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        self._image = QLabel()
        self._image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image.setWordWrap(True)
        self._image.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        image_font = self._image.font()
        image_font.setPointSize(max(8, image_font.pointSize() - 1))
        self._image.setFont(image_font)
        layout.addWidget(self._image, 0, Qt.AlignmentFlag.AlignHCenter)

        self._caption = QLabel()
        self._caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._caption.setWordWrap(True)
        caption_font = self._caption.font()
        caption_font.setPointSize(max(8, caption_font.pointSize() - 2))
        self._caption.setFont(caption_font)
        layout.addWidget(self._caption)

        self._apply_thumb_size(thumb_width)
        self._apply_style()

    def oracle_id(self) -> str:
        return self._oracle_id

    def card_name(self) -> str:
        return self._caption.text()

    def owner_id(self) -> int:
        return self._owner

    def cancel_pending(self) -> None:
        # Invalidate deferred load_image callbacks from a previous bind.
        self._bind_generation += 1
        image_loader().cancel(self._owner)

    def bind(self, row: InventorySummaryRow, *, selected: bool) -> None:
        """Attach a card to this tile.

        Same-card rebinds are cheap (selection/caption only) so scroll sync can
        call this without decoding or rescaling art on every pixel.
        """
        same_card = row.oracle_id == self._oracle_id
        if same_card:
            if self._caption.text() != row.card_name:
                self._card_name = row.card_name
                self._caption.setText(row.card_name)
            self.set_selected(selected)
            return

        self.cancel_pending()
        self._oracle_id = row.oracle_id
        self._card_name = row.card_name
        self._caption.setText(row.card_name)
        self.set_selected(selected)
        self._source_pixmap = None
        self._show_placeholder(loading=True)
        # Defer disk/network work so scroll can paint placeholders first.
        self._bind_generation += 1
        generation = self._bind_generation
        QTimer.singleShot(0, lambda g=generation: self._load_after_bind(g))

    def _load_after_bind(self, generation: int) -> None:
        if generation != self._bind_generation:
            return
        self.load_image_if_needed()

    def set_selected(self, selected: bool) -> None:
        if self._selected == selected:
            return
        self._selected = selected
        self._apply_style()

    def retranslate(self) -> None:
        if self._source_pixmap is None and self._oracle_id:
            self._show_placeholder()

    def set_thumb_width(self, width: int) -> None:
        if width == self._thumb_width:
            return
        self._apply_thumb_size(width)
        self._rescale()

    def load_image_if_needed(self) -> None:
        if not self._oracle_id:
            return
        if self._source_pixmap is not None:
            self._rescale()
            return

        known, cached = _cached_pixmap(self._oracle_id)
        if known:
            if cached is not None:
                self._source_pixmap = cached
                self._rescale()
            else:
                self._show_placeholder(loading=False)
            return

        pixmap = load_local_pixmap(self._oracle_id)
        if pixmap is not None:
            self._source_pixmap = pixmap
            self._rescale()
            return

        # Not on disk yet — marked slot, then ensure_image in the background.
        self._show_placeholder(loading=True)
        image_loader().request(self._owner, self._oracle_id, False)

    def apply_resolved(self, oracle_id: str, pixmap: QPixmap | None) -> None:
        if oracle_id != self._oracle_id:
            return
        if pixmap is None or pixmap.isNull():
            mark_image_unavailable(oracle_id)
            self._source_pixmap = None
            self._show_placeholder(loading=False)
            return
        _store_pixmap(oracle_id, pixmap)
        self._source_pixmap = pixmap
        self._rescale()

    def _apply_thumb_size(self, width: int) -> None:
        self._thumb_width = width
        height = thumb_height_for_width(width)
        self._image.setFixedSize(width, height)
        self.setFixedSize(width + TILE_PADDING, height + CAPTION_EXTRA)

    def _rescale(self) -> None:
        if self._source_pixmap is None:
            if self._oracle_id:
                self._show_placeholder()
            return
        self._image.setText("")
        self._image.setToolTip("")
        self._apply_image_face_style(placeholder=False)
        self._image.setPixmap(
            self._source_pixmap.scaled(
                QSize(self._thumb_width, thumb_height_for_width(self._thumb_width)),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
        )

    def _show_placeholder(self, *, loading: bool | None = None) -> None:
        """Card-shaped slot with name + status while the image loads or if ensure fails."""
        if loading is not None:
            self._placeholder_loading = loading
        key = (
            "inventory.view.loading_image"
            if self._placeholder_loading
            else "inventory.view.missing_image"
        )
        message = self._translator.t(key)
        self._image.setPixmap(QPixmap())
        self._image.setText(message)
        self._image.setToolTip(message)
        self._apply_image_face_style(placeholder=True)

    def _apply_image_face_style(self, *, placeholder: bool) -> None:
        """Keep the face rectangle the same tile color whether art is present or not."""
        if placeholder:
            self._image.setStyleSheet(
                "QLabel {"
                " background: palette(base);"
                " color: palette(text);"
                " border: 1px solid palette(mid);"
                " border-radius: 2px;"
                " padding: 10px;"
                "}"
            )
            return
        self._image.setStyleSheet("")

    def _apply_style(self) -> None:
        border = "#4a90d9" if self._selected else "palette(mid)"
        width = 2 if self._selected else 1
        self.setStyleSheet(
            f"#inventoryCardTile {{"
            f" border: {width}px solid {border};"
            f" border-radius: 4px;"
            f" background: palette(base);"
            f"}}"
        )

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.button() == Qt.MouseButton.LeftButton and self._oracle_id:
            self.clicked.emit(self._oracle_id)
        super().mousePressEvent(event)


class InventoryImageGrid(QScrollArea):
    """Virtualized grid of card faces from the local image cache (max 5 per row)."""

    card_selected = Signal(str)

    def __init__(
        self,
        translator: Translator,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._translator = translator
        self._rows: list[InventorySummaryRow] = []
        self._tiles: dict[int, _CardTile] = {}
        self._pool: list[_CardTile] = []
        self._selected_oracle_id: str | None = None
        self._thumb_width = THUMB_MIN_WIDTH
        self._pending_rows: list[InventorySummaryRow] | None = None
        self._last_viewport_size: tuple[int, int] = (0, 0)

        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(50)
        self._resize_timer.timeout.connect(self._apply_responsive_size)

        self._populate_timer = QTimer(self)
        self._populate_timer.setSingleShot(True)
        self._populate_timer.setInterval(0)
        self._populate_timer.timeout.connect(self._flush_pending_rows)

        self._geometry_sync_timer = QTimer(self)
        self._geometry_sync_timer.setSingleShot(True)
        self._geometry_sync_timer.setInterval(0)
        self._geometry_sync_timer.timeout.connect(self._resync_if_geometry_changed)

        self.setWidgetResizable(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)

        self._container = QWidget()
        self._container.setMinimumWidth(1)
        self.setWidget(self._container)
        image_loader().resolved.connect(self._on_image_resolved)

    def set_rows(self, rows: list[InventorySummaryRow]) -> None:
        # Defer so the stacked-widget switch can paint before we mount tiles.
        self._pending_rows = list(rows)
        self._populate_timer.start()

    def ensure_layout_sync(self) -> None:
        """Re-run geometry + visible tiles after the stacked view is laid out."""
        if self._pending_rows is not None:
            self._flush_pending_rows()
        else:
            self._thumb_width = self._compute_thumb_width()
            self._update_container_geometry()
            self._clamp_scroll()
            self._sync_visible_tiles()
        self._schedule_geometry_resync()
        # Preview/layout can settle one tick later when nothing was selected.
        QTimer.singleShot(0, self._remount_if_empty)

    def selected_oracle_id(self) -> str | None:
        return self._selected_oracle_id

    def mounted_indices(self) -> list[int]:
        """Flat indices that currently have a tile widget (visible window)."""
        return sorted(self._tiles)

    def tile_at(self, index: int) -> _CardTile | None:
        return self._tiles.get(index)

    def select_oracle_id(self, oracle_id: str | None) -> None:
        self._selected_oracle_id = oracle_id
        for index, tile in self._tiles.items():
            row = self._rows[index] if 0 <= index < len(self._rows) else None
            tile.set_selected(
                row is not None and row.oracle_id == oracle_id
            )

    def retranslate(self) -> None:
        for tile in self._tiles.values():
            tile.retranslate()
        for tile in self._pool:
            tile.retranslate()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 (Qt override)
        super().resizeEvent(event)
        self._resize_timer.start()

    def showEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().showEvent(event)
        if self._pending_rows is not None:
            self._flush_pending_rows()
        else:
            self._sync_visible_tiles()
        self._schedule_geometry_resync()

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        key = event.key()
        if key in (
            Qt.Key.Key_Left,
            Qt.Key.Key_Right,
            Qt.Key.Key_Up,
            Qt.Key.Key_Down,
            Qt.Key.Key_Home,
            Qt.Key.Key_End,
        ):
            if self._move_selection(key):
                event.accept()
                return
        if (
            key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space)
            and self._selected_oracle_id
        ):
            self.card_selected.emit(self._selected_oracle_id)
            event.accept()
            return
        super().keyPressEvent(event)

    def _index_of_selected(self) -> int | None:
        if self._selected_oracle_id is None:
            return None
        for index, row in enumerate(self._rows):
            if row.oracle_id == self._selected_oracle_id:
                return index
        return None

    def _move_selection(self, key: int) -> bool:
        total = len(self._rows)
        if total <= 0:
            return False

        current = self._index_of_selected()
        if key == Qt.Key.Key_Home:
            new_index = 0
        elif key == Qt.Key.Key_End:
            new_index = total - 1
        elif current is None:
            # First arrow with no selection → start of the list.
            new_index = 0
        elif key == Qt.Key.Key_Left:
            new_index = move_grid_index(
                current, d_col=-1, total=total, columns=GRID_COLUMNS, wrap=True
            )
        elif key == Qt.Key.Key_Right:
            new_index = move_grid_index(
                current, d_col=1, total=total, columns=GRID_COLUMNS, wrap=True
            )
        elif key == Qt.Key.Key_Up:
            new_index = move_grid_index(
                current, d_row=-1, total=total, columns=GRID_COLUMNS
            )
        elif key == Qt.Key.Key_Down:
            new_index = move_grid_index(
                current, d_row=1, total=total, columns=GRID_COLUMNS
            )
        else:
            return False

        if new_index is None:
            return False

        oracle_id = self._rows[new_index].oracle_id
        self.select_oracle_id(oracle_id)
        self._ensure_index_visible(new_index)
        self._sync_visible_tiles()
        self.card_selected.emit(oracle_id)
        return True

    def _ensure_index_visible(self, index: int) -> None:
        x, y = tile_top_left(index, self._thumb_width)
        tile_w, tile_h = tile_outer_size(self._thumb_width)
        # Pin both corners so the full tile stays in the viewport.
        self.ensureVisible(x, y, 1, 1)
        self.ensureVisible(x + tile_w - 1, y + tile_h - 1, 1, 1)

    def _flush_pending_rows(self) -> None:
        if self._pending_rows is None:
            return
        rows = self._pending_rows
        self._pending_rows = None
        self._rows = rows
        self._thumb_width = self._compute_thumb_width()
        self._update_container_geometry()
        self._clamp_scroll()
        self._recycle_all_tiles()
        self._sync_visible_tiles()
        self._schedule_geometry_resync()

    def _clamp_scroll(self) -> None:
        """Keep the bar inside the new content range before mounting tiles."""
        bar = self.verticalScrollBar()
        bar.setValue(min(max(bar.value(), bar.minimum()), bar.maximum()))

    def _remount_if_empty(self) -> None:
        """Recover from stacked-switch races that left data but no tiles."""
        if not self._rows or self._tiles or not self.isVisible():
            return
        self._thumb_width = self._compute_thumb_width()
        self._update_container_geometry()
        self._clamp_scroll()
        self._sync_visible_tiles()

    def _compute_thumb_width(self) -> int:
        return thumb_width_for_viewport(max(self.viewport().width(), 1))

    def _viewport_size(self) -> tuple[int, int]:
        vp = self.viewport()
        return vp.width(), vp.height()

    def _update_container_geometry(self) -> None:
        width = max(self.viewport().width(), 1)
        height = content_height(len(self._rows), self._thumb_width)
        self._container.setFixedSize(width, height)

    def _apply_responsive_size(self) -> None:
        width = self._compute_thumb_width()
        size_changed = width != self._thumb_width
        self._thumb_width = width
        self._update_container_geometry()
        self._clamp_scroll()
        if size_changed:
            for tile in self._tiles.values():
                tile.set_thumb_width(width)
            for tile in self._pool:
                tile.set_thumb_width(width)
            # Positions depend on thumb size — remount.
            self._recycle_all_tiles()
        self._sync_visible_tiles()
        self._last_viewport_size = self._viewport_size()

    def _on_scroll(self, _value: int) -> None:
        # Mount immediately — debounce left a frame with recycled tiles and empty bands.
        self._sync_visible_tiles()

    def _schedule_geometry_resync(self) -> None:
        """Re-sync on the next tick if stacked layout changed viewport size."""
        self._last_viewport_size = self._viewport_size()
        self._geometry_sync_timer.start()

    def _resync_if_geometry_changed(self) -> None:
        size = self._viewport_size()
        empty_but_has_rows = bool(self._rows) and not self._tiles
        if (
            size == self._last_viewport_size
            and size[1] > 0
            and not empty_but_has_rows
        ):
            return
        self._thumb_width = self._compute_thumb_width()
        self._update_container_geometry()
        self._clamp_scroll()
        self._sync_visible_tiles()
        self._last_viewport_size = size
        if self._rows and not self._tiles:
            # Layout still not ready — try once more next tick.
            QTimer.singleShot(0, self._remount_if_empty)

    def _recycle_all_tiles(self) -> None:
        for tile in self._tiles.values():
            tile.cancel_pending()
            tile.hide()
            self._pool.append(tile)
        self._tiles.clear()

    def _acquire_tile(self) -> _CardTile:
        if self._pool:
            tile = self._pool.pop()
            tile.set_thumb_width(self._thumb_width)
            tile.show()
            return tile
        tile = _CardTile(
            self._translator,
            self._container,
            thumb_width=self._thumb_width,
        )
        tile.clicked.connect(self._on_tile_clicked)
        # Children added to an already-visible parent stay hidden until shown.
        tile.show()
        return tile

    def _sync_visible_tiles(self) -> None:
        start, end = visible_index_range(
            self.verticalScrollBar().value(),
            self.viewport().height(),
            self._thumb_width,
            len(self._rows),
        )
        needed = set(range(start, end))
        structure_changed = False

        for index in list(self._tiles):
            if index not in needed:
                tile = self._tiles.pop(index)
                tile.cancel_pending()
                tile.hide()
                self._pool.append(tile)
                structure_changed = True

        for index in range(start, end):
            row = self._rows[index]
            selected = row.oracle_id == self._selected_oracle_id
            tile = self._tiles.get(index)
            if tile is None:
                tile = self._acquire_tile()
                self._tiles[index] = tile
                tile.bind(row, selected=selected)
                x, y = tile_top_left(index, self._thumb_width)
                tile.move(x, y)
                structure_changed = True
                continue

            # Index already mounted: keep art; only rebind if the card changed.
            if tile.oracle_id() != row.oracle_id:
                tile.bind(row, selected=selected)
                structure_changed = True
            else:
                tile.set_selected(selected)

        if structure_changed:
            self._container.update()
            self.viewport().update()

    def _on_image_resolved(
        self,
        oracle_id: str,
        back: bool,
        image: object,
        _has_back: bool,
    ) -> None:
        if back:
            return
        pixmap: QPixmap | None = None
        if isinstance(image, QImage) and not image.isNull():
            pixmap = QPixmap.fromImage(image)
        elif isinstance(image, QPixmap) and not image.isNull():
            pixmap = image
        for tile in self._tiles.values():
            if tile.oracle_id() == oracle_id:
                tile.apply_resolved(oracle_id, pixmap)
        # Cache failure even if no tile still shows this card.
        if pixmap is None or pixmap.isNull():
            mark_image_unavailable(oracle_id)

    def _on_tile_clicked(self, oracle_id: str) -> None:
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        self.select_oracle_id(oracle_id)
        self.card_selected.emit(oracle_id)
