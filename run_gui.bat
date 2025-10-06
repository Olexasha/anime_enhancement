@echo off
REM Batch file для запуска GUI на Windows
REM Убедитесь, что вы находитесь в корневой директории проекта

echo Starting Anime Enhancement GUI...
echo.

REM Проверяем наличие Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python не найден в PATH
    echo Установите Python 3.12+ и добавьте его в PATH
    pause
    exit /b 1
)

REM Проверяем наличие main.py
if not exist "main.py" (
    echo ERROR: Файл main.py не найден
    echo Убедитесь, что вы запускаете из корневой директории проекта
    pause
    exit /b 1
)

REM Проверяем наличие settings.py
if not exist "src\config\settings.py" (
    echo ERROR: Файл src\config\settings.py не найден
    echo Убедитесь, что структура проекта корректна
    pause
    exit /b 1
)

REM Устанавливаем зависимости, если нужно
if not exist "venv" (
    echo Создание виртуального окружения...
    python -m venv venv
)

echo Активация виртуального окружения...
call venv\Scripts\activate.bat

echo Установка зависимостей...
pip install -r requirements-gui.txt

echo.
echo Запуск GUI...
python gui\app.py

pause
