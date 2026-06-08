#!/usr/bin/env sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$ROOT"

if [ -x ".venv/bin/python" ]; then
  PYTHON=".venv/bin/python"
elif [ -x "venv/bin/python" ]; then
  PYTHON="venv/bin/python"
else
  PYTHON="python3"
fi

echo "Запуск GUI anime_enhancement..."
"$PYTHON" gui/app.py
