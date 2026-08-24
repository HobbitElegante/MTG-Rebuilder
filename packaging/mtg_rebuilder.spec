# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir spec for MTG-Rebuilder (Linux AppImage + Windows folder)."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

ROOT = Path(SPECPATH).resolve().parent
ALEMBIC_DIR = ROOT / "src" / "mtg_rebuilder" / "database" / "alembic"
RESOURCES_DIR = ROOT / "src" / "mtg_rebuilder" / "resources"

datas = [
    (str(ALEMBIC_DIR), "mtg_rebuilder/database/alembic"),
    (str(RESOURCES_DIR), "mtg_rebuilder/resources"),
]
binaries = []
hiddenimports = [
    "alembic",
    "logging.config",
    "sqlalchemy",
    "PySide6",
    "httpx",
    "ortools",
    "ortools.linear_solver.pywraplp",
]
hiddenimports += collect_submodules("alembic")
hiddenimports += collect_submodules("mtg_rebuilder")

for pkg in ("PySide6", "ortools", "alembic"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

a = Analysis(
    [str(ROOT / "src" / "mtg_rebuilder" / "__main__.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=sorted(set(hiddenimports)),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MTG-Rebuilder",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="MTG-Rebuilder",
)
