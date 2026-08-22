"""Pure layout helpers for the Inventory image grid (no Qt).

Kept separate from ``widgets.inventory_image_grid`` so CI headless tests can
exercise geometry / path logic without importing PySide6 (needs libEGL).
"""

from pathlib import Path

from mtg_rebuilder.services.card_image_service import image_path_for

GRID_COLUMNS = 5
# Scryfall "normal" aspect 488x680.
CARD_ASPECT = 680 / 488
CAPTION_EXTRA = 28  # name label + spacing under the image
TILE_PADDING = 8  # left+right (or top) frame margins around the image
GRID_H_SPACING = 10
GRID_V_SPACING = 10
GRID_MARGIN = 4
THUMB_MIN_WIDTH = 140
THUMB_MAX_WIDTH = 280
# Extra rows above/below the viewport so scroll rarely leaves empty bands.
SCROLL_BUFFER_ROWS = 4
# When the stacked view syncs before layout, still mount several rows.
PRELAYOUT_MIN_ROWS = 3


def grid_cell_position(index: int, columns: int = GRID_COLUMNS) -> tuple[int, int]:
    """Return (row, col) for a flat index in a fixed-column grid."""
    if columns < 1:
        raise ValueError("columns must be >= 1")
    return divmod(index, columns)


def move_grid_index(
    index: int,
    *,
    d_row: int = 0,
    d_col: int = 0,
    total: int,
    columns: int = GRID_COLUMNS,
    wrap: bool = False,
) -> int | None:
    """Return a new flat index after a row/col step, or None if out of bounds.

    Left/right use ``d_col`` (±1); with *wrap* they continue onto the next or
    previous row (end of row -> leftmost card below). Up/down use ``d_row``
    (±1) and keep the column.
    """
    if total <= 0 or columns < 1:
        return None
    if index < 0 or index >= total:
        return None
    if d_col and wrap:
        new_index = index + d_col
        if new_index < 0 or new_index >= total:
            return None
        return new_index
    row, col = divmod(index, columns)
    new_row = row + d_row
    new_col = col + d_col
    if new_col < 0 or new_col >= columns or new_row < 0:
        return None
    new_index = new_row * columns + new_col
    if new_index >= total:
        return None
    return new_index


def grid_row_count(n: int, columns: int = GRID_COLUMNS) -> int:
    """Number of grid rows needed for *n* cells."""
    if n <= 0:
        return 0
    if columns < 1:
        raise ValueError("columns must be >= 1")
    return (n + columns - 1) // columns


def thumb_width_for_viewport(
    viewport_width: int,
    *,
    columns: int = GRID_COLUMNS,
    spacing: int = GRID_H_SPACING,
    margin: int = GRID_MARGIN,
    tile_padding: int = TILE_PADDING,
    min_width: int = THUMB_MIN_WIDTH,
    max_width: int = THUMB_MAX_WIDTH,
) -> int:
    """Image width that fills the viewport with *columns* tiles per row."""
    if columns < 1:
        raise ValueError("columns must be >= 1")
    usable = viewport_width - (2 * margin) - ((columns - 1) * spacing)
    cell = usable // columns
    image_width = cell - tile_padding
    return max(min_width, min(max_width, image_width))


def thumb_height_for_width(width: int) -> int:
    return int(width * CARD_ASPECT)


def tile_outer_size(thumb_width: int) -> tuple[int, int]:
    """Widget size (w, h) for a tile at the given image width."""
    return (
        thumb_width + TILE_PADDING,
        thumb_height_for_width(thumb_width) + CAPTION_EXTRA,
    )


def row_stride(thumb_width: int, *, v_spacing: int = GRID_V_SPACING) -> int:
    """Vertical distance from one grid row to the next (tile height + spacing)."""
    return tile_outer_size(thumb_width)[1] + v_spacing


def content_height(
    n: int,
    thumb_width: int,
    *,
    columns: int = GRID_COLUMNS,
    margin: int = GRID_MARGIN,
    v_spacing: int = GRID_V_SPACING,
) -> int:
    """Total scrollable content height for *n* cards."""
    rows = grid_row_count(n, columns)
    if rows == 0:
        return 2 * margin
    tile_h = tile_outer_size(thumb_width)[1]
    return (2 * margin) + (rows * tile_h) + ((rows - 1) * v_spacing)


def visible_index_range(
    scroll_y: int,
    viewport_height: int,
    thumb_width: int,
    total: int,
    *,
    columns: int = GRID_COLUMNS,
    buffer_rows: int = SCROLL_BUFFER_ROWS,
) -> tuple[int, int]:
    """Inclusive-start / exclusive-end flat indices that should be mounted.

    Always returns a contiguous row-aligned window (no holes in the middle).
    If *total* > 0 the window is never empty (stale scroll past the end is clamped).
    """
    if total <= 0:
        return 0, 0
    # Stacked-widget switches can sync before layout gives a real height —
    # mount several leading rows so the first paint is not a grey void.
    if viewport_height <= 0:
        rows = max(PRELAYOUT_MIN_ROWS, 1 + buffer_rows)
        return 0, min(total, columns * rows)
    stride = row_stride(thumb_width)
    if stride <= 0:
        return 0, total
    first_row = max(0, (scroll_y - GRID_MARGIN) // stride - buffer_rows)
    last_row = (
        (scroll_y + viewport_height - GRID_MARGIN) // stride + buffer_rows
    )
    start = first_row * columns
    end = min(total, (last_row + 1) * columns)
    if start >= total:
        # Scroll still past the end after a shrink / stacked switch — last page.
        rows_to_show = max(PRELAYOUT_MIN_ROWS, 1 + buffer_rows)
        first_row = max(0, grid_row_count(total, columns) - rows_to_show)
        start = first_row * columns
        end = total
    return start, max(start, end)


def tile_top_left(
    index: int,
    thumb_width: int,
    *,
    columns: int = GRID_COLUMNS,
    margin: int = GRID_MARGIN,
    h_spacing: int = GRID_H_SPACING,
    v_spacing: int = GRID_V_SPACING,
) -> tuple[int, int]:
    """Pixel (x, y) for the top-left of the tile at *index*."""
    row, col = grid_cell_position(index, columns)
    tile_w, tile_h = tile_outer_size(thumb_width)
    x = margin + col * (tile_w + h_spacing)
    y = margin + row * (tile_h + v_spacing)
    return x, y


def local_front_image_path(oracle_id: str, images_dir: Path | None = None) -> Path | None:
    """Path to the on-disk front face, or None if not downloaded yet."""
    path = image_path_for(oracle_id, images_dir)
    return path if path.is_file() else None
