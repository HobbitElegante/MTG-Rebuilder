from pathlib import Path

from mtg_rebuilder.i18n import Translator
from mtg_rebuilder.services.browse_service import InventorySummaryRow
from mtg_rebuilder.ui.inventory_display import format_inventory_detail_lines
from mtg_rebuilder.ui.inventory_image_layout import (
    GRID_COLUMNS,
    PRELAYOUT_MIN_ROWS,
    SCROLL_BUFFER_ROWS,
    content_height,
    grid_cell_position,
    grid_row_count,
    local_front_image_path,
    move_grid_index,
    row_stride,
    thumb_height_for_width,
    thumb_width_for_viewport,
    tile_outer_size,
    tile_top_left,
    visible_index_range,
)


def test_grid_cell_position() -> None:
    assert grid_cell_position(0) == (0, 0)
    assert grid_cell_position(4) == (0, 4)
    assert grid_cell_position(5) == (1, 0)
    assert grid_cell_position(6) == (1, 1)


def test_move_grid_index() -> None:
    assert move_grid_index(0, d_col=1, total=12) == 1
    assert move_grid_index(4, d_col=1, total=12) is None  # end of row
    assert move_grid_index(5, d_col=-1, total=12) is None  # start of row
    assert move_grid_index(5, d_row=-1, total=12) == 0
    assert move_grid_index(0, d_row=-1, total=12) is None
    assert move_grid_index(7, d_row=1, total=12) is None  # 7+5 → past end
    assert move_grid_index(6, d_row=1, total=12) == 11
    assert move_grid_index(0, d_col=-1, total=0) is None


def test_move_grid_index_wraps_rows() -> None:
    """Right at the end of a row continues on the leftmost card below."""
    assert move_grid_index(4, d_col=1, total=12, wrap=True) == 5
    assert move_grid_index(5, d_col=-1, total=12, wrap=True) == 4
    assert move_grid_index(11, d_col=1, total=12, wrap=True) is None  # last card
    assert move_grid_index(0, d_col=-1, total=12, wrap=True) is None  # first card
    # Vertical moves never wrap, even with the flag on.
    assert move_grid_index(2, d_row=-1, total=12, wrap=True) is None


def test_grid_row_count() -> None:
    assert grid_row_count(0) == 0
    assert grid_row_count(1) == 1
    assert grid_row_count(5) == 1
    assert grid_row_count(6) == 2
    assert GRID_COLUMNS == 5


def test_thumb_width_fills_viewport() -> None:
    # 5 cols, spacing 10*4=40, margins 8, padding 8 → image uses leftover evenly.
    width = thumb_width_for_viewport(
        900, columns=5, spacing=10, margin=4, tile_padding=8, min_width=140, max_width=280
    )
    # usable = 900 - 8 - 40 = 852; cell = 170; image = 162
    assert width == 162
    assert thumb_height_for_width(width) == int(162 * 680 / 488)


def test_thumb_width_clamped_to_min_max() -> None:
    assert thumb_width_for_viewport(200, min_width=140, max_width=280) == 140
    assert thumb_width_for_viewport(2000, min_width=140, max_width=280) == 280


def test_scroll_buffer_default() -> None:
    assert SCROLL_BUFFER_ROWS >= 3
    assert PRELAYOUT_MIN_ROWS >= 2


def test_visible_index_range_window() -> None:
    thumb = 140
    start, end = visible_index_range(
        scroll_y=0,
        viewport_height=500,
        thumb_width=thumb,
        total=100,
        buffer_rows=0,
    )
    assert start == 0
    assert end > 0
    assert end <= 100
    assert start % GRID_COLUMNS == 0

    start2, end2 = visible_index_range(
        scroll_y=800,
        viewport_height=400,
        thumb_width=thumb,
        total=100,
        buffer_rows=1,
    )
    assert start2 > 0
    assert start2 < end2 <= 100
    assert start2 % GRID_COLUMNS == 0


def test_visible_index_range_scroll_past_end_not_empty() -> None:
    """Stale scrollbar past content must still mount a last page of tiles."""
    thumb = 140
    total = 20
    start, end = visible_index_range(
        scroll_y=1_000_000,
        viewport_height=500,
        thumb_width=thumb,
        total=total,
        buffer_rows=1,
    )
    assert 0 <= start < end <= total
    assert end == total


def test_visible_index_range_covers_viewport_mid_scroll() -> None:
    """Mounted window must cover the full viewport plus buffer (no logical holes)."""
    thumb = 140
    scroll_y = 800
    viewport_height = 500
    total = 200
    buffer = SCROLL_BUFFER_ROWS
    start, end = visible_index_range(
        scroll_y=scroll_y,
        viewport_height=viewport_height,
        thumb_width=thumb,
        total=total,
        buffer_rows=buffer,
    )
    assert 0 <= start < end <= total
    assert start % GRID_COLUMNS == 0
    # Contiguous flat range — every index between start and end is a candidate tile.
    assert end - start == len(range(start, end))

    first_y = tile_top_left(start, thumb)[1]
    last_y = tile_top_left(end - 1, thumb)[1]
    tile_h = tile_outer_size(thumb)[1]
    assert first_y <= scroll_y
    assert last_y + tile_h >= scroll_y + viewport_height

    # Span covers at least viewport rows + 2 * buffer.
    stride = row_stride(thumb)
    mounted_rows = (end - start + GRID_COLUMNS - 1) // GRID_COLUMNS
    visible_rows = max(1, (viewport_height + stride - 1) // stride)
    assert mounted_rows >= visible_rows


def test_visible_index_range_before_layout() -> None:
    """Zero viewport height must still expose several leading rows (stacked switch)."""
    start, end = visible_index_range(
        scroll_y=0,
        viewport_height=0,
        thumb_width=140,
        total=40,
        buffer_rows=0,
    )
    assert start == 0
    assert end == GRID_COLUMNS * PRELAYOUT_MIN_ROWS
    start_buf, end_buf = visible_index_range(
        0, 0, 140, 40, buffer_rows=SCROLL_BUFFER_ROWS
    )
    assert start_buf == 0
    assert end_buf == GRID_COLUMNS * max(PRELAYOUT_MIN_ROWS, 1 + SCROLL_BUFFER_ROWS)
    assert visible_index_range(0, 0, 140, 0) == (0, 0)


def test_content_height_scales_with_rows() -> None:
    assert content_height(0, 140) == 8
    one = content_height(1, 140)
    five = content_height(5, 140)
    six = content_height(6, 140)
    assert one == five  # one row
    assert six > five


def test_tile_top_left_second_row() -> None:
    x, y = tile_top_left(5, 140)
    assert x == 4  # margin, col 0
    assert y > 4


def test_local_front_image_path_missing(tmp_path: Path) -> None:
    assert local_front_image_path("missing-oid", tmp_path) is None


def test_local_front_image_path_present(tmp_path: Path) -> None:
    path = tmp_path / "present-oid.jpg"
    path.write_bytes(b"fake")
    assert local_front_image_path("present-oid", tmp_path) == path


def test_format_inventory_detail_lines_without_edition() -> None:
    translator = Translator("en")
    row = InventorySummaryRow(
        oracle_id="oid",
        card_name="Sol Ring",
        total_copies=3,
        free_copies=1,
        assigned_decks=("Kellan",),
        color_identity="",
        cmc=1.0,
        mana_cost="{1}",
        rarity="uncommon",
        rarities=frozenset({"uncommon"}),
        editions=(("C21", 2), (None, 1)),
    )
    lines = dict(format_inventory_detail_lines(row, translator, track_editions=False))
    assert "Edition" not in lines
    assert lines["Name"] == "Sol Ring"
    assert lines["CMC"] == "1"
    assert lines["Mana"] == "1"
    assert lines["Colors"] == "—"
    assert lines["Rarity"] == "U"
    assert lines["Total"] == "3"
    assert lines["Free"] == "1"
    assert lines["Assigned"] == "2"
    assert lines["In decks"] == "Kellan"


def test_format_inventory_detail_lines_with_edition() -> None:
    translator = Translator("en")
    row = InventorySummaryRow(
        oracle_id="oid",
        card_name="Sol Ring",
        total_copies=2,
        free_copies=2,
        assigned_decks=(),
        editions=(("C21", 2),),
    )
    lines = dict(format_inventory_detail_lines(row, translator, track_editions=True))
    assert lines["Edition"] == "C21"


def test_missing_image_i18n_kept_for_tooltip() -> None:
    assert "Oops" in Translator("en").t("inventory.view.loading_image")
    assert "Oops" in Translator("es").t("inventory.view.loading_image")
    assert "Remember" in Translator("en").t("inventory.view.missing_image")
    assert "Recuerda" in Translator("es").t("inventory.view.missing_image")
