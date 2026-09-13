"""Static assets shipped with the package.

They live inside `mtg_rebuilder` so the same path resolves from a source
checkout, an installed wheel and the PyInstaller bundle (the spec copies this
directory to `mtg_rebuilder/resources`).
"""

from pathlib import Path

_RESOURCES = Path(__file__).resolve().parent

APP_ICON = _RESOURCES / "app_icon.png"
CARD_SYMBOLS_DIR = _RESOURCES / "card-symbols"

__all__ = ["APP_ICON", "CARD_SYMBOLS_DIR"]
