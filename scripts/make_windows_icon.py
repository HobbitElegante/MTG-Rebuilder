#!/usr/bin/env python
"""Regenerate packaging/mtg_rebuilder.ico from the packaged 256x256 app icon.

PyInstaller needs a real ``.ico`` to stamp the Windows ``.exe``; Qt can only
write single-image ones, so the container is assembled here. Run it after
editing ``resources/app_icon.png`` and commit the result:

    uv run python scripts/make_windows_icon.py

Sizes that divide 256 are scaled nearest-neighbour to keep the pixel art
crisp; 48 (Explorer's medium icons) is the only smoothed one.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, Qt
from PySide6.QtGui import QImage

from mtg_rebuilder.resources import APP_ICON

# Windows picks the closest match; 256 must be PNG-compressed by convention.
BMP_SIZES = (16, 32, 48, 64, 128)
PNG_SIZE = 256

ICO_PATH = Path(__file__).resolve().parent.parent / "packaging" / "mtg_rebuilder.ico"


def _scaled(source: QImage, size: int) -> QImage:
    mode = (
        Qt.TransformationMode.FastTransformation
        if PNG_SIZE % size == 0
        else Qt.TransformationMode.SmoothTransformation
    )
    return source.scaled(
        size, size, Qt.AspectRatioMode.IgnoreAspectRatio, mode
    ).convertToFormat(QImage.Format.Format_ARGB32)


def _dib_bytes(image: QImage) -> bytes:
    """32-bit BITMAPINFOHEADER icon image: BGRA rows bottom-up + empty mask."""
    width, height = image.width(), image.height()
    header = struct.pack(
        "<IiiHHIIiiII",
        40,  # biSize
        width,
        height * 2,  # biHeight covers the XOR image plus the AND mask
        1,  # biPlanes
        32,  # biBitCount
        0,  # biCompression (BI_RGB)
        width * height * 4,  # biSizeImage
        0,
        0,
        0,
        0,
    )
    # Format_ARGB32 is BGRA in memory on little-endian, which is what DIB wants.
    if sys.byteorder != "little":  # pragma: no cover - CI and dev are x86_64
        raise RuntimeError("big-endian hosts need a channel swap here")
    bits = image.constBits()
    stride = image.bytesPerLine()
    rows = [
        bytes(bits[y * stride : y * stride + width * 4])
        for y in range(height - 1, -1, -1)
    ]
    # Alpha drives transparency for 32-bit icons, so the mask is all-opaque.
    mask_stride = ((width + 31) // 32) * 4
    return header + b"".join(rows) + b"\x00" * (mask_stride * height)


def _png_bytes(image: QImage) -> bytes:
    # QBuffer must own its QByteArray here: a Python-side temporary would be
    # freed while Qt still points at it.
    buffer = QBuffer()
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise RuntimeError("Qt could not encode the 256x256 PNG entry")
    return bytes(buffer.data())


def build_ico(source_png: Path, target: Path) -> Path:
    source = QImage(str(source_png))
    if source.isNull():
        raise RuntimeError(f"Could not read {source_png}")
    images = [(size, _dib_bytes(_scaled(source, size))) for size in BMP_SIZES]
    images.append((PNG_SIZE, _png_bytes(_scaled(source, PNG_SIZE))))

    offset = 6 + 16 * len(images)
    directory = b""
    for size, payload in images:
        directory += struct.pack(
            "<BBBBHHII",
            0 if size >= 256 else size,  # 0 means 256 in the ICO directory
            0 if size >= 256 else size,
            0,  # palette size (none)
            0,  # reserved
            1,  # planes
            32,  # bits per pixel
            len(payload),
            offset,
        )
        offset += len(payload)

    target.write_bytes(
        struct.pack("<HHH", 0, 1, len(images))
        + directory
        + b"".join(payload for _size, payload in images)
    )
    return target


def main() -> int:
    written = build_ico(APP_ICON, ICO_PATH)
    sizes = ", ".join(str(size) for size in (*BMP_SIZES, PNG_SIZE))
    print(f"Wrote {written} ({written.stat().st_size} bytes; sizes {sizes})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
