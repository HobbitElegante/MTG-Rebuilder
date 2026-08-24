#!/usr/bin/env bash
# Install (or uninstall) a user-local .desktop entry for the MTG Rebuilder AppImage.
# Places the binary under ~/.local/share/mtg-rebuilder and registers it in the
# application menu — similar to unzipping the Windows zip and keeping the .exe.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARCH="$(uname -m)"

INSTALL_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/mtg-rebuilder"
APPIMAGE_DEST="$INSTALL_DIR/MTG-Rebuilder.AppImage"
DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
DESKTOP_FILE="$DESKTOP_DIR/mtg-rebuilder.desktop"
ICON_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/256x256/apps"
ICON_FILE="$ICON_DIR/mtg-rebuilder.png"
PACKAGING_ICON="$ROOT/src/mtg_rebuilder/resources/app_icon.png"
# Previous install layout (pre-rename); cleaned on uninstall / overwritten on install.
LEGACY_INSTALL_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/mtg-sorter"
LEGACY_DESKTOP_FILE="$DESKTOP_DIR/mtg-sorter.desktop"
LEGACY_ICON_FILE="$ICON_DIR/mtg-sorter.png"

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS] [APPIMAGE]

Install the AppImage into ~/.local and register a .desktop entry in the
application menu (no root required). Database and images stay in the
platform user-data dir and are not touched.

Arguments:
  APPIMAGE   Path to MTG-Rebuilder-*.AppImage
             Default: $ROOT/dist/MTG-Rebuilder-${ARCH}.AppImage (if present)

Options:
  --uninstall   Remove the installed AppImage, .desktop, and icon
  -h, --help    Show this help
EOF
}

refresh_caches() {
  if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
  fi
  local icon_root
  icon_root="$(dirname "$(dirname "$(dirname "$ICON_DIR")")")"
  if command -v gtk-update-icon-cache >/dev/null 2>&1 && [[ -d "$icon_root" ]]; then
    gtk-update-icon-cache -f -t "$icon_root" 2>/dev/null || true
  fi
}

remove_legacy_menu_entries() {
  rm -f "$LEGACY_DESKTOP_FILE" "$LEGACY_ICON_FILE"
  rm -f "$LEGACY_INSTALL_DIR/MTG-Sorter.AppImage"
  rmdir "$LEGACY_INSTALL_DIR" 2>/dev/null || true
}

do_uninstall() {
  rm -f "$DESKTOP_FILE" "$ICON_FILE" "$APPIMAGE_DEST"
  rmdir "$INSTALL_DIR" 2>/dev/null || true
  remove_legacy_menu_entries
  refresh_caches
  echo "Uninstalled desktop entry and AppImage from $INSTALL_DIR"
  echo "User data (database + images) was left in place."
}

extract_icon_from_appimage() {
  local appimage="$1"
  local tmp
  tmp="$(mktemp -d)"
  # AppImage offset extraction; fall back silently if the tool/layout differs.
  if (cd "$tmp" && APPIMAGE_EXTRACT_AND_RUN=1 "$appimage" --appimage-extract mtg-rebuilder.png >/dev/null 2>&1) \
    && [[ -f "$tmp/squashfs-root/mtg-rebuilder.png" ]]; then
    cp "$tmp/squashfs-root/mtg-rebuilder.png" "$ICON_FILE"
    rm -rf "$tmp"
    return 0
  fi
  rm -rf "$tmp"
  return 1
}

install_icon() {
  local appimage="$1"
  mkdir -p "$ICON_DIR"
  if [[ -f "$PACKAGING_ICON" ]]; then
    cp "$PACKAGING_ICON" "$ICON_FILE"
    return 0
  fi
  if extract_icon_from_appimage "$appimage"; then
    return 0
  fi
  echo "warning: could not install icon ($PACKAGING_ICON missing and AppImage extract failed)" >&2
  return 1
}

write_desktop_file() {
  local exec_path="$1"
  local has_icon="$2"
  mkdir -p "$DESKTOP_DIR"
  local icon_value="mtg-rebuilder"
  if [[ "$has_icon" != "1" ]]; then
    # Absolute fallback keeps the entry valid without a theme icon.
    icon_value="$exec_path"
  fi
  cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=MTG Rebuilder
Name[es]=MTG Rebuilder
Comment=MTG Commander collection manager
Comment[es]=Administrador de colección Commander de MTG
Exec=${exec_path}
Icon=${icon_value}
Categories=Game;CardGame;
Keywords=Magic;MTG;Commander;deck;inventory;collection;
StartupWMClass=MTG-Rebuilder
Terminal=false
EOF
}

do_install() {
  local appimage="$1"
  if [[ ! -f "$appimage" ]]; then
    echo "error: AppImage not found: $appimage" >&2
    exit 1
  fi
  appimage="$(cd "$(dirname "$appimage")" && pwd)/$(basename "$appimage")"

  mkdir -p "$INSTALL_DIR"
  cp "$appimage" "$APPIMAGE_DEST"
  chmod +x "$APPIMAGE_DEST"

  local has_icon=0
  if install_icon "$APPIMAGE_DEST"; then
    has_icon=1
  fi

  write_desktop_file "$APPIMAGE_DEST" "$has_icon"
  remove_legacy_menu_entries
  refresh_caches

  echo "Installed:"
  echo "  AppImage: $APPIMAGE_DEST"
  echo "  Desktop:  $DESKTOP_FILE"
  if [[ "$has_icon" == "1" ]]; then
    echo "  Icon:     $ICON_FILE"
  fi
  echo "Open “MTG Rebuilder” from your application menu, or run:"
  echo "  $APPIMAGE_DEST"
}

MODE=install
APPIMAGE_ARG=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --uninstall)
      MODE=uninstall
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    -*)
      echo "error: unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
    *)
      if [[ -n "$APPIMAGE_ARG" ]]; then
        echo "error: unexpected argument: $1" >&2
        usage >&2
        exit 1
      fi
      APPIMAGE_ARG="$1"
      shift
      ;;
  esac
done

if [[ "$MODE" == "uninstall" ]]; then
  do_uninstall
  exit 0
fi

DEFAULT_APPIMAGE="$ROOT/dist/MTG-Rebuilder-${ARCH}.AppImage"
APPIMAGE="${APPIMAGE_ARG:-}"
if [[ -z "$APPIMAGE" ]]; then
  if [[ -f "$DEFAULT_APPIMAGE" ]]; then
    APPIMAGE="$DEFAULT_APPIMAGE"
  else
    echo "error: no AppImage path given and default not found:" >&2
    echo "  $DEFAULT_APPIMAGE" >&2
    usage >&2
    exit 1
  fi
fi

do_install "$APPIMAGE"
