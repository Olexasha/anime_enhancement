#!/usr/bin/env sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$ROOT"

echo "Установка anime_enhancement"

if command -v python3.13 >/dev/null 2>&1; then
  PYTHON=python3.13
elif command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON=python
else
  echo "Python не найден. Установите Python 3.13." >&2
  exit 1
fi

VERSION="$($PYTHON -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')"
$PYTHON - <<'PY'
import sys
if sys.version_info < (3, 13) or sys.version_info >= (3, 14):
    raise SystemExit('Требуется Python 3.13.x.')
PY

echo "Используется Python $VERSION"

if [ -d venv ]; then
  echo "Найдена старая папка venv. Удалите ее или переименуйте: $ROOT/venv" >&2
  exit 1
fi

if [ ! -d .venv ]; then
  echo "Создание единого виртуального окружения .venv на Python $VERSION"
  "$PYTHON" -m venv .venv
fi

VENV_PYTHON="$ROOT/.venv/bin/python"
VENV_VERSION="$($VENV_PYTHON -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')"
case "$VENV_VERSION" in
  3.13.*) ;;
  *) echo ".venv создан не на Python 3.13, найден $VENV_VERSION. Удалите .venv и повторите install.sh." >&2; exit 1 ;;
esac

echo "Окружение .venv использует Python $VENV_VERSION"
"$VENV_PYTHON" -m pip install --upgrade pip poetry
POETRY_VIRTUALENVS_CREATE=false "$VENV_PYTHON" -m poetry install --no-root

if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  echo "FFmpeg не найден. Попытка подсказать установку для текущей ОС."
  "$VENV_PYTHON" scripts/install_ffmpeg.py || true
fi

echo "Проверка окружения"
"$VENV_PYTHON" main.py --check-environment || true

echo "Установка завершена."
echo "Запуск GUI: ./run_gui.sh"
echo "Запуск CLI: .venv/bin/python main.py --config profiles/profile.json"
