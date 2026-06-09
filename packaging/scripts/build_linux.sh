#!/usr/bin/env sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
cd "$ROOT"

if [ "$(uname -s)" != "Linux" ]; then
  echo "build_linux.sh нужно запускать на Linux. Каждая ОС собирается на своей ОС." >&2
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

echo "Подготовка app-local FFmpeg для portable"
poetry run python scripts/install_ffmpeg.py --ensure-local

echo "Проверка pyproject"
poetry check
echo "Ruff check"
poetry run ruff check .
echo "Pytest"
poetry run pytest

echo "Очистка Linux build/dist/release"
rm -rf build dist/AnimeEnhancement release/linux
mkdir -p release/linux

echo "Сборка PyInstaller one-folder для Linux"
poetry run pyinstaller --noconfirm packaging/pyinstaller/AnimeEnhancement.linux.spec

if [ ! -x dist/AnimeEnhancement/AnimeEnhancement ]; then
  echo "Не найден Linux binary: dist/AnimeEnhancement/AnimeEnhancement" >&2
  exit 1
fi
if [ ! -x dist/AnimeEnhancement/AnimeEnhancementCLI ]; then
  echo "Не найден Linux CLI helper: dist/AnimeEnhancement/AnimeEnhancementCLI" >&2
  exit 1
fi

cp packaging/linux/README_LINUX.txt dist/AnimeEnhancement/README_LINUX.txt

for tool in \
  src/utils/realesrgan/realesrgan-linux/realesrgan-ncnn-vulkan \
  src/utils/waifu2x/waifu2x-linux/waifu2x-ncnn-vulkan \
  src/utils/rife/rife-linux/rife-ncnn-vulkan
 do
  if [ ! -x "$tool" ]; then
    echo "ПРЕДУПРЕЖДЕНИЕ: Linux binary отсутствует или не исполняемый: $tool" >&2
  fi
 done

TAR_PATH="$ROOT/release/linux/AnimeEnhancement-Linux.tar.gz"
tar -czf "$TAR_PATH" -C dist AnimeEnhancement

echo "Linux portable archive создан: $TAR_PATH"
echo "Если FFmpeg не bundled, установите ffmpeg через пакетный менеджер."
