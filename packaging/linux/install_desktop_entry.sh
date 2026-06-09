#!/usr/bin/env sh
set -eu

APP_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
DESKTOP_SRC="$APP_DIR/packaging/linux/assets/anime-enhancement.desktop"
ICON_SRC="$APP_DIR/assets/branding/icon.png"
DESKTOP_DST="${XDG_DATA_HOME:-$HOME/.local/share}/applications/anime-enhancement.desktop"
ICON_DST="${XDG_DATA_HOME:-$HOME/.local/share}/icons/anime_enhancement.png"

mkdir -p "$(dirname "$DESKTOP_DST")" "$(dirname "$ICON_DST")"
cp "$ICON_SRC" "$ICON_DST"
sed "s|^Icon=.*|Icon=$ICON_DST|" "$DESKTOP_SRC" > "$DESKTOP_DST"

echo "Desktop entry установлен для текущего пользователя: $DESKTOP_DST"
echo "При необходимости обновите Exec= в desktop-файле на путь к portable binary."
