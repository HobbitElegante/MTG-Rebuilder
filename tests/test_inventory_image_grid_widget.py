"""Widget-level tests for the Inventory image grid.

Skipped wherever PySide6 cannot be imported; the CI runner has the package but
not the Qt system libs, so the import fails with a plain ``ImportError``
(``libEGL.so.1``) rather than ``ModuleNotFoundError``. ``pytest.importorskip``
only catches the latter since pytest 9.1, hence the explicit guard below.
The Qt-free geometry helpers are covered by ``test_inventory_image_view.py``.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QEvent, QObject, Qt, Signal
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QApplication

    from mtg_rebuilder.i18n import Translator
    from mtg_rebuilder.services.browse_service import InventorySummaryRow
    from mtg_rebuilder.ui import inventory_image_layout as layout
    from mtg_rebuilder.ui.widgets import inventory_image_grid as grid_module
except ImportError as exc:  # pragma: no cover - headless CI without Qt libs
    pytest.skip(f"PySide6 unavailable: {exc}", allow_module_level=True)

GRID_WIDTH = 900


class _StubLoader(QObject):
    """Stands in for the shared image loader: no threads, no DB, no network."""

    resolved = Signal(str, bool, object, bool)

    def __init__(self) -> None:
        super().__init__()
        self.requests: list[tuple[int, str, bool]] = []

    def request(self, owner: int, oracle_id: str, back: bool) -> None:
        self.requests.append((owner, oracle_id, back))

    def cancel(self, owner: int) -> None:
        self.requests = [item for item in self.requests if item[0] != owner]


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def stub_loader(monkeypatch):
    loader = _StubLoader()
    monkeypatch.setattr(grid_module, "image_loader", lambda: loader)
    return loader


def _rows(count: int) -> list[InventorySummaryRow]:
    return [
        InventorySummaryRow(
            oracle_id=f"oid-{index:03d}",
            card_name=f"Card {index:03d}",
            total_copies=1,
            free_copies=1,
            assigned_decks=(),
        )
        for index in range(count)
    ]


def _settle(app: QApplication, rounds: int = 4) -> None:
    for _ in range(rounds):
        app.processEvents()


def _make_grid(app: QApplication, *, cards: int, height: int):
    grid = grid_module.InventoryImageGrid(Translator("en"))
    grid.resize(GRID_WIDTH, height)
    grid.show()
    _settle(app)
    grid.set_rows(_rows(cards))
    _settle(app)
    grid.ensure_layout_sync()
    _settle(app)
    return grid


def _press(grid, key: Qt.Key) -> None:
    grid.keyPressEvent(
        QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
    )


def test_mounted_tiles_are_visible_and_named(qapp, stub_loader) -> None:
    """Every mounted index must have a shown tile carrying the card name."""
    grid = _make_grid(qapp, cards=60, height=700)
    try:
        indices = grid.mounted_indices()
        assert indices, "no tiles mounted for a non-empty inventory"
        for index in indices:
            tile = grid.tile_at(index)
            assert tile is not None
            assert tile.isVisible(), f"tile {index} mounted but hidden"
            assert tile.card_name() == f"Card {index:03d}"
    finally:
        grid.deleteLater()


def test_growing_window_keeps_every_tile_visible(qapp, stub_loader) -> None:
    """Enlarging the window needs more tiles than the pool holds — the new
    ones used to stay hidden, leaving empty blocks until the user scrolled."""
    grid = _make_grid(qapp, cards=60, height=300)
    try:
        before = len(grid.mounted_indices())

        grid.resize(GRID_WIDTH, 1200)
        # Fire what the debounced resize timer would run.
        grid._apply_responsive_size()
        _settle(qapp)

        indices = grid.mounted_indices()
        assert len(indices) > before, "taller viewport should mount more tiles"
        hidden = [i for i in indices if not grid.tile_at(i).isVisible()]
        assert hidden == [], f"tiles mounted but hidden after resize: {hidden}"
        blank = [i for i in indices if not grid.tile_at(i).card_name()]
        assert blank == [], f"tiles without a card name after resize: {blank}"
    finally:
        grid.deleteLater()


def test_narrowing_and_widening_keeps_tiles_visible(qapp, stub_loader) -> None:
    """Width changes rescale thumbs and remount every tile from the pool."""
    grid = _make_grid(qapp, cards=60, height=700)
    try:
        for width in (600, 1400, GRID_WIDTH):
            grid.resize(width, 700)
            grid._apply_responsive_size()
            _settle(qapp)
            indices = grid.mounted_indices()
            assert indices
            hidden = [i for i in indices if not grid.tile_at(i).isVisible()]
            assert hidden == [], f"hidden tiles at width {width}: {hidden}"
    finally:
        grid.deleteLater()


def test_populates_without_a_previous_selection(qapp, stub_loader) -> None:
    """Switching table -> images with nothing selected must still show cards."""
    grid = grid_module.InventoryImageGrid(Translator("en"))
    grid.resize(GRID_WIDTH, 700)
    try:
        grid.set_rows(_rows(40))
        grid.select_oracle_id(None)
        grid.show()
        _settle(qapp)
        grid.ensure_layout_sync()
        _settle(qapp)

        assert grid.selected_oracle_id() is None
        indices = grid.mounted_indices()
        assert indices
        assert 0 in indices
        assert all(grid.tile_at(i).isVisible() for i in indices)
    finally:
        grid.deleteLater()


def test_stale_scroll_past_content_still_mounts(qapp, stub_loader) -> None:
    """A shorter list after filtering must not leave the grid blank."""
    grid = _make_grid(qapp, cards=200, height=700)
    try:
        bar = grid.verticalScrollBar()
        bar.setValue(bar.maximum())
        _settle(qapp)

        grid.set_rows(_rows(12))
        _settle(qapp)
        grid.ensure_layout_sync()
        _settle(qapp)

        indices = grid.mounted_indices()
        assert indices, "grid went blank after the list shrank"
        assert all(grid.tile_at(i).isVisible() for i in indices)
    finally:
        grid.deleteLater()


def test_arrow_right_wraps_to_next_row(qapp, stub_loader) -> None:
    grid = _make_grid(qapp, cards=40, height=700)
    try:
        last_of_row = layout.GRID_COLUMNS - 1
        grid.select_oracle_id(f"oid-{last_of_row:03d}")

        _press(grid, Qt.Key.Key_Right)
        assert grid.selected_oracle_id() == f"oid-{layout.GRID_COLUMNS:03d}"

        _press(grid, Qt.Key.Key_Left)
        assert grid.selected_oracle_id() == f"oid-{last_of_row:03d}"
    finally:
        grid.deleteLater()


def test_arrows_walk_the_whole_grid(qapp, stub_loader) -> None:
    """Holding Right must reach the last card without dead ends at row edges."""
    total = 23
    grid = _make_grid(qapp, cards=total, height=700)
    try:
        grid.select_oracle_id("oid-000")
        for _ in range(total - 1):
            _press(grid, Qt.Key.Key_Right)
        assert grid.selected_oracle_id() == f"oid-{total - 1:03d}"

        # Past the end it stays put instead of wrapping around to the start.
        _press(grid, Qt.Key.Key_Right)
        assert grid.selected_oracle_id() == f"oid-{total - 1:03d}"
    finally:
        grid.deleteLater()


def test_arrow_down_scrolls_and_mounts_target(qapp, stub_loader) -> None:
    grid = _make_grid(qapp, cards=200, height=500)
    try:
        grid.select_oracle_id("oid-000")
        for _ in range(20):
            _press(grid, Qt.Key.Key_Down)
        _settle(qapp)

        selected = grid.selected_oracle_id()
        assert selected == f"oid-{20 * layout.GRID_COLUMNS:03d}"
        index = 20 * layout.GRID_COLUMNS
        assert index in grid.mounted_indices()
        assert grid.tile_at(index).isVisible()
    finally:
        grid.deleteLater()
