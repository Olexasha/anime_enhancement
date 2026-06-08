#!/usr/bin/env sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
cd "$ROOT"

if [ "$(uname -s)" != "Darwin" ]; then
  echo "build_macos.sh нужно запускать на macOS. Каждая ОС собирается на своей ОС." >&2
  exit 1
fi

if ! command -v poetry >/dev/null 2>&1; then
  echo "Poetry не найден. Установите Poetry или выполните dev/bootstrap install.sh." >&2
  exit 1
fi

PY_VERSION="$(poetry run python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')"
case "$PY_VERSION" in
  3.13.*) ;;
  *) echo "Требуется Python 3.13.x в Poetry-окружении, найден $PY_VERSION" >&2; exit 1 ;;
esac

echo "Poetry окружение: Python $PY_VERSION"
echo "Установка зависимостей через Poetry"
poetry install --no-root

echo "Проверка pyproject"
poetry check
echo "Ruff check"
poetry run ruff check .
echo "Pytest"
poetry run pytest

if [ ! -f packaging/macos/assets/anime_enhancement.icns ]; then
  echo "ПРЕДУПРЕЖДЕНИЕ: anime_enhancement.icns отсутствует. Сборка продолжится без app icon." >&2
  echo "Инструкция по генерации: packaging/macos/assets/ICNS_TODO.txt" >&2
fi

echo "Очистка macOS build/dist/release"
rm -rf build dist/AnimeEnhancement dist/AnimeEnhancement.app release/macos
mkdir -p release/macos

echo "Сборка PyInstaller .app для macOS"
poetry run pyinstaller --noconfirm packaging/pyinstaller/AnimeEnhancement.macos.spec

if [ ! -d dist/AnimeEnhancement.app ]; then
  echo "Не найден app bundle: dist/AnimeEnhancement.app" >&2
  exit 1
fi

for tool in \
  src/utils/realesrgan/realesrgan-macos/realesrgan-ncnn-vulkan \
  src/utils/waifu2x/waifu2x-macos/waifu2x-ncnn-vulkan \
  src/utils/rife/rife-macos/rife-ncnn-vulkan
 do
  if [ ! -x "$tool" ]; then
    echo "ПРЕДУПРЕЖДЕНИЕ: macOS binary отсутствует или не исполняемый: $tool" >&2
  fi
 done

ZIP_PATH="$ROOT/release/macos/AnimeEnhancement-macOS.zip"
( cd dist && ditto -c -k --sequesterRsrc --keepParent AnimeEnhancement.app "$ZIP_PATH" )

echo "macOS zip создан: $ZIP_PATH"
echo "DMG пока не собирается автоматически; это следующий шаг после проверки .app на macOS."
