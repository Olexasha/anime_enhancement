#!/bin/bash
# Shell script для запуска GUI на Linux/macOS
# Убедитесь, что вы находитесь в корневой директории проекта

echo "Starting Anime Enhancement GUI..."
echo

# Проверяем наличие Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python3 не найден в PATH"
    echo "Установите Python 3.12+ и добавьте его в PATH"
    exit 1
fi

# Проверяем версию Python
python_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
required_version="3.12"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "ERROR: Требуется Python $required_version или выше, найден $python_version"
    exit 1
fi

# Проверяем наличие main.py
if [ ! -f "main.py" ]; then
    echo "ERROR: Файл main.py не найден"
    echo "Убедитесь, что вы запускаете из корневой директории проекта"
    exit 1
fi

# Проверяем наличие settings.py
if [ ! -f "src/config/settings.py" ]; then
    echo "ERROR: Файл src/config/settings.py не найден"
    echo "Убедитесь, что структура проекта корректна"
    exit 1
fi

# Создаем виртуальное окружение, если нужно
if [ ! -d "venv" ]; then
    echo "Создание виртуального окружения..."
    python3 -m venv venv
fi

echo "Активация виртуального окружения..."
source venv/bin/activate

echo "Установка зависимостей..."
pip install -r requirements-gui.txt

echo
echo "Запуск GUI..."
python gui/app.py
