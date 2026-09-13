# Packaging

Build portable binaries with **PyInstaller** (`onedir`). Linux wraps the folder in an **AppImage**. Windows produces `dist/MTG-Rebuilder/MTG-Rebuilder.exe` and zips it for distribution.

**Version / tag:** **`1.2.0`** — Inventory filter chips + color modes + CMC guards, Scryfall mana symbols (tier B), Qt window icon, filter dialog rework (subtypes / free-copies). Bump the version here and in `pyproject.toml` / `src/mtg_rebuilder/__init__.py` before the next tag. Test count before tagging: `uv run pytest` (currently **384**).

Published builds appear on the repository **Releases** page when a version tag is pushed.

## Requirements

- Python 3.13+ and [uv](https://docs.astral.sh/uv/)
- Optional extra: `uv sync --extra packaging`
- Linux AppImage: `curl` (script downloads `appimagetool` into `tools/`). FUSE helps; without it (or in CI) the script uses `APPIMAGE_EXTRACT_AND_RUN=1`.

## Linux

```bash
./scripts/build_linux.sh
```

Output: `dist/MTG-Rebuilder-x86_64.AppImage` (arch name follows `uname -m`).

Smoke with an isolated data dir:

```bash
TMP=$(mktemp -d)
MTG_REBUILDER_DATA_DIR="$TMP" QT_QPA_PLATFORM=offscreen APPIMAGE_EXTRACT_AND_RUN=1 \
  ./dist/MTG-Rebuilder-x86_64.AppImage &
# then quit the window / kill the process; check $TMP/mtg_rebuilder.db exists
```

### Application menu (user-local `.desktop`)

Register the AppImage in the desktop menu without root (mirrors “unzip Windows zip → keep the `.exe`”):

```bash
./scripts/install_linux_desktop.sh                    # uses dist/MTG-Rebuilder-$(uname -m).AppImage
./scripts/install_linux_desktop.sh /path/to/app.AppImage
./scripts/install_linux_desktop.sh --uninstall
```

Installs to:

| What | Path |
|------|------|
| AppImage | `~/.local/share/mtg-rebuilder/MTG-Rebuilder.AppImage` |
| Desktop entry | `~/.local/share/applications/mtg-rebuilder.desktop` |
| Icon | `~/.local/share/icons/hicolor/256x256/apps/mtg-rebuilder.png` |

Source icon in the repo: `src/mtg_rebuilder/resources/app_icon.png` (**256×256** RGBA) — single source for the AppImage, this install script and the Qt window icon (`main.py` calls `setWindowIcon`, so `uv run` and the Windows exe get it too). It lives inside the package on purpose: the same path resolves from a checkout, a wheel and the PyInstaller bundle (the spec copies `resources/` into `mtg_rebuilder/resources`). On Wayland the compositor ignores that icon and matches `setDesktopFileName("mtg-rebuilder")` against the installed `.desktop` instead, so run the install script to see it there.

Does **not** touch the SQLite DB / card images (XDG user-data). The AppImage-embedded `packaging/mtg-rebuilder.desktop` is unchanged in role (`Exec=MTG-Rebuilder` for appimagetool).

Without a repo checkout, friends can still `chmod +x` and run the AppImage from Downloads; the install script is the optional menu step.

## Windows

Run on Windows (or `windows-latest` in GitHub Actions):

```powershell
.\scripts\build_windows.ps1
```

Output:

- `dist\MTG-Rebuilder\MTG-Rebuilder.exe`
- `dist\MTG-Rebuilder-windows-x64.zip` (folder zipped for Releases)

## Publishing a GitHub Release

CI builds and publishes automatically when you **push a version tag**. Binaries are listed on the release for that tag (and at `/releases/latest`).

### Checklist (each version)

1. Code ready on `main` — local tests green: `uv run pytest`.
2. Version string in `pyproject.toml` / `src/mtg_rebuilder/__init__.py` / README Features+Latest matches the tag you will create (e.g. `1.2.0`).
3. Commit and push:
   ```bash
   git push origin main
   ```
4. Create and push the tag:
   ```bash
   git tag v1.2.0
   git push origin v1.2.0
   ```
5. Open the repo **Actions** tab — wait for the **Release** workflow (tests + Linux AppImage + Windows zip). Often ~10–20 minutes.
6. Open **Releases** — `v1.2.0` should list the AppImage and the Windows zip.
7. Optional: edit the release notes.

### If the workflow fails

1. Open the red job log in **Actions** and fix the issue on `main`.
2. Either bump to a new tag (`v1.2.1`) after pushing the fix, or delete the bad tag and recreate it on the fixed commit (keeps the same version string):
   ```bash
   git tag -d v1.2.0
   git push origin :refs/tags/v1.2.0
   git tag v1.2.0
   git push origin v1.2.0
   ```

Known headless pitfalls already handled in `.github/workflows/release.yml`:

- Do **not** install `pytest-qt` in the test job (it auto-loads Qt). Entry point name is `pytest-qt` (hyphen), not `pytestqt`.
- `ui/__init__.py` must stay lazy so formatter tests do not import PySide6.
- Layout helpers for Inventory image view live in `ui/inventory_image_layout.py` (no Qt); the same goes for `ui/inventory_display.py` (chip labels, button counter) and `ui/filter_picker.py` (picker resolution). Widget tests for the grid (`tests/test_inventory_image_grid_widget.py`) run locally with `QT_QPA_PLATFORM=offscreen` and skip on the runner. The filter-dialog and chip-bar tests (`tests/test_inventory_filter_dialog_widget.py`, `tests/test_chip_bar_widget.py`) follow the same rule. Guard them with an explicit `try/except ImportError` + `pytest.skip(..., allow_module_level=True)`, **not** `pytest.importorskip`: PySide6 *is* installed on the runner and fails with a plain `ImportError: libEGL.so.1`, while `importorskip` only catches `ModuleNotFoundError` since pytest 9.1.
- To rehearse the runner locally, shadow PySide6 with a stub that raises `ImportError` and disable the plugin that auto-loads Qt: `PYTHONPATH=/tmp/noqt uv run pytest -q -p no:pytest-qt` (expect the widget modules to skip, not error).
- Linux build needs system libs (`libegl1`, …) because PyInstaller imports PySide6.

### Prerequisite

The packaging scripts, workflow (`.github/workflows/release.yml`), and related code must already be on the commit you tag. Tagging an old commit will not include AppImage/Windows builds.

## Notes

- User data (SQLite + images) goes to the platform user-data dir when frozen; override with `MTG_REBUILDER_DATA_DIR`.
- Alembic migration scripts are bundled under `_MEIPASS/mtg_rebuilder/database/alembic`.
- Workflow file: [`.github/workflows/release.yml`](../.github/workflows/release.yml).
- **Smoke Windows-like UI on Linux:** `QT_STYLE_OVERRIDE=Windows uv run mtg-rebuilder` (forces the Qt Windows style; useful for layout bugs that only show under the native style, e.g. zero-width combos). Not a substitute for a real Windows VM when validating the `.exe`.
- **Combo standard:** every data `QComboBox` should go through `mtg_rebuilder.ui.combo.configure_data_combo` (minimum contents length). Do not nest a `QGroupBox` that only wraps a combo inside another group box — that collapsed Language/Theme under native Windows in `v0.9.3`.
