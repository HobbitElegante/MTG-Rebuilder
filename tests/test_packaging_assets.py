"""The Windows .exe icon must stay a valid multi-size ICO wired to the spec.

Mirrors how PyInstaller reads it (``utils/win32/icon.py``): signature check,
then the directory entries, then one resource per image. A broken container
only shows up as a generic .exe icon in a released zip, so it is guarded here.
"""

import struct
from pathlib import Path

ICO_SIGNATURE = b"\x00\x00\x01\x00"
EXPECTED_SIZES = {16, 32, 48, 64, 128, 256}

_PACKAGING = Path(__file__).resolve().parent.parent / "packaging"
ICO_PATH = _PACKAGING / "mtg_rebuilder.ico"
SPEC_PATH = _PACKAGING / "mtg_rebuilder.spec"


def _entries(blob: bytes) -> list[tuple[int, int, int, int]]:
    """(size, bits per pixel, byte length, offset) per image in the directory."""
    _reserved, _type, count = struct.unpack_from("<HHH", blob, 0)
    out = []
    for index in range(count):
        width, _height, _colors, _pad, _planes, bpp, length, offset = struct.unpack_from(
            "<BBBBHHII", blob, 6 + 16 * index
        )
        out.append((width or 256, bpp, length, offset))
    return out


def test_windows_icon_is_a_multi_size_ico():
    blob = ICO_PATH.read_bytes()
    assert blob[:4] == ICO_SIGNATURE
    entries = _entries(blob)
    assert {size for size, *_rest in entries} == EXPECTED_SIZES
    for size, bpp, length, offset in entries:
        assert bpp == 32, size
        assert length > 0, size
        assert offset + length <= len(blob), size


def test_pyinstaller_spec_points_at_the_windows_icon():
    spec = SPEC_PATH.read_text(encoding="utf-8")
    assert ICO_PATH.name in spec
    assert "icon=str(WINDOWS_ICON)" in spec
