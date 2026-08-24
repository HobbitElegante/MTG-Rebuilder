"""The app icon must travel with the package (wheel + PyInstaller bundle)."""

from mtg_rebuilder.resources import APP_ICON

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def test_app_icon_is_bundled_with_the_package():
    assert APP_ICON.is_file()
    assert APP_ICON.parent.name == "resources"


def test_app_icon_is_a_readable_png():
    assert APP_ICON.read_bytes()[:8] == PNG_MAGIC
