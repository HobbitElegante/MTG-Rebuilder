"""Static assets shipped with the package.

They live inside `mtg_rebuilder` so the same path resolves from a source
checkout, an installed wheel and the PyInstaller bundle (the spec copies this
directory to `mtg_rebuilder/resources`).
"""

from pathlib import Path

APP_ICON = Path(__file__).resolve().parent / "app_icon.png"

__all__ = ["APP_ICON"]
