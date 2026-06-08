#!/usr/bin/env sh
set -eu

APP_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
DESKTOP_SRC="$APP_DIR/packaging/linux/assets/anime-enhancement.desktop"
ICON_SRC="$APP_DIR/packaging/linux/assets/anime_enhancement.png"
DESKTOP_DST="${XDG_DATA_HOME:-$HOME/.local/share}/applications/anime-enhancement.desktop"
ICON_DST="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/1024x1024/apps/anime_enhancement.png"

mkdir -p "$(dirname "$DESKTOP_DST")" "$(dirname "$ICON_DST")"
cp "$DESKTOP_SRC" "$DESKTOP_DST"
cp "$ICON_SRC" "$ICON_DST"

echo "Desktop entry установлен для текущего пользователя: $DESKTOP_DST"
echo "При необходимости обновите Exec= в desktop-файле на путь к portable binary."
