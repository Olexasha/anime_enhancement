# Anime Enhancement

Anime Enhancement — desktop/CLI-приложение для улучшения старого аниме-видео, в первую очередь Naruto. Пайплайн извлекает кадры, запускает AI-утилиты для denoise/upscale/interpolation, собирает видео обратно и копирует аудио из оригинала.

## Возможности

- Извлечение кадров через FFmpeg.
- Опциональный denoise через waifu2x-ncnn-vulkan.
- Апскейл через RealESRGAN-ncnn-vulkan.
- Интерполяция кадров через RIFE-ncnn-vulkan.
- Сборка промежуточных и финальных видео через FFmpeg.
- Копирование аудиодорожки из оригинала без обязательного перекодирования.
- GUI на PySide6 и CLI используют один пайплайн и JSON-профили.

## Поддержка платформ

- Windows: основная поддерживаемая релизная платформа. Готовится PyInstaller one-folder build и Inno Setup installer.
- Linux: experimental portable-сборка. Работает только при наличии Linux binaries для RealESRGAN/waifu2x/RIFE и установленного или bundled FFmpeg.
- macOS: experimental `.app` skeleton. Работает только при наличии macOS binaries для RealESRGAN/waifu2x/RIFE и установленного или bundled FFmpeg.

Каждая ОС собирается на своей ОС. Не пытайтесь собрать полноценный Windows `.exe` на Linux или macOS `.app` на Windows.

## Для обычного пользователя

### Windows

1. Откройте GitHub Releases.
2. Скачайте `AnimeEnhancementSetup.exe`.
3. Запустите installer и откройте Anime Enhancement из меню Пуск или ярлыка.

Пользовательский installer не требует ручной установки Python, Poetry, `.venv` или Python-зависимостей.

### Linux

1. Скачайте `AnimeEnhancement-Linux.tar.gz` из GitHub Releases.
2. Распакуйте архив.
3. Запустите binary:

```bash
./AnimeEnhancement
```

Если FFmpeg не включен в portable-сборку, установите его через пакетный менеджер, например:

```bash
sudo apt install ffmpeg
```

### macOS

1. Скачайте `AnimeEnhancement-macOS.zip` или будущий `.dmg` из GitHub Releases.
2. Распакуйте архив.
3. Откройте `AnimeEnhancement.app`.

Если FFmpeg не включен в bundle, установите его через Homebrew:

```bash
brew install ffmpeg
```

## Для разработчика

Основное dev-окружение единое: Python 3.13.2 + Poetry.

### Windows bootstrap

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1
```

### Linux/macOS bootstrap

```bash
chmod +x install.sh run_gui.sh
./install.sh
```

`install.ps1` и `install.sh` — dev/bootstrap-скрипты для запуска из исходников. Это не пользовательские installer-ы и их не нужно предлагать обычному пользователю вместо GitHub Release артефактов.

### CLI запуск из исходников

```bash
python main.py
python main.py --config profiles/profile.json
python main.py --check-environment
```

### GUI запуск из исходников

```bash
python -m gui.app
```

или через dev helper:

```bash
./run_gui.sh
```

## Сборка релиза

### Windows

Запускать на Windows:

```powershell
.\packaging\scripts\build_windows.ps1 -ZipPortable
```

Результат:

- `dist/AnimeEnhancement/AnimeEnhancement.exe` — portable GUI build.
- `dist/AnimeEnhancement/AnimeEnhancementCLI.exe` — helper для запуска пайплайна из GUI без Python.
- `release/windows/AnimeEnhancementSetup.exe` — Inno Setup installer, если найден `ISCC.exe`.
- `release/windows/AnimeEnhancement-Windows.zip` — portable zip, если указан `-ZipPortable`.

Если Inno Setup не установлен, скрипт честно выведет инструкцию и оставит готовый portable build в `dist/AnimeEnhancement`.

### Linux

Запускать на Linux:

```bash
chmod +x packaging/scripts/build_linux.sh
./packaging/scripts/build_linux.sh
```

Результат:

- `dist/AnimeEnhancement/AnimeEnhancement` — portable GUI binary.
- `dist/AnimeEnhancement/AnimeEnhancementCLI` — helper для запуска пайплайна из GUI.
- `release/linux/AnimeEnhancement-Linux.tar.gz` — portable archive.

### macOS

Запускать на macOS:

```bash
chmod +x packaging/scripts/build_macos.sh
./packaging/scripts/build_macos.sh
```

Результат:

- `dist/AnimeEnhancement.app` — app bundle.
- `release/macos/AnimeEnhancement-macOS.zip` — zip для GitHub Releases.

DMG пока не собирается автоматически. Инструкция по генерации `.icns` лежит в `packaging/macos/assets/ICNS_TODO.txt`.

## build, dist и release

- `build/` — промежуточная техническая папка PyInstaller. Пользователю ее не показывать и exe из нее не запускать.
- `dist/` — portable-сборка программы после PyInstaller.
- `release/` — финальные файлы, которые можно выкладывать в GitHub Releases.

## Почему нет одного installer на все ОС

Windows, Linux и macOS используют разные форматы приложений, разные бинарники AI-утилит и разные правила установки. Один “магический” installer на все ОС был бы ненадежным и misleading. В проекте общая packaging-архитектура, но разные сборочные скрипты и артефакты под каждую платформу.

## Assets

Общие branding assets:

- `assets/branding/anime_enhancement_logo_1024.png`
- `assets/branding/banner_1200x380.png`
- `assets/branding/icon.png` — исходник иконки приложения/ярлыков.

Windows assets:

- `packaging/windows/assets/anime_enhancement.ico` — Windows `.ico` для приложения, ярлыков и установщика.
- `packaging/windows/assets/wizard-small.bmp`
- `packaging/windows/assets/wizard-large.bmp`

Linux assets:

- `packaging/linux/assets/anime_enhancement.png`
- `packaging/linux/assets/anime-enhancement.desktop`

macOS assets:

- `packaging/macos/assets/anime_enhancement.icns` — нужно создать на macOS, если нужен app icon.

Лицензия используется из корневого файла `LICENSE`. Копии `LICENSE.txt` в platform assets не нужны.

## Внешние бинарники

Проект использует:

- `ffmpeg` и `ffprobe`;
- `realesrgan-ncnn-vulkan`;
- `waifu2x-ncnn-vulkan`;
- `rife-ncnn-vulkan`.

Windows `.exe` binaries не подходят для Linux/macOS. Linux и macOS требуют свои binaries в соответствующих папках `src/utils/*/*-linux` и `src/utils/*/*-macos`. Dependency checker выводит ошибку на русском, если binary для текущей ОС отсутствует.

FFmpeg ищется так:

1. app-local bundled location внутри portable/app сборки или `tools/ffmpeg`;
2. системный `PATH`.

Приложение не меняет глобальный `PATH` пользователя.

## Пути данных

Код не должен зависеть от текущей рабочей директории. В dev-режиме ресурсы ищутся в корне репозитория. Во frozen-режиме ресурсы ищутся внутри portable/app bundle, а пользовательские профили, логи и рабочие данные пишутся в пользовательские директории:

- Windows: `%LOCALAPPDATA%\AnimeEnhancement`.
- Linux: `$XDG_DATA_HOME/anime-enhancement` или `~/.local/share/anime-enhancement`.
- macOS: `~/Library/Application Support/AnimeEnhancement`.

## Что выкладывать в GitHub Release

Windows:

- `release/windows/AnimeEnhancementSetup.exe` — основной пользовательский артефакт.
- `release/windows/AnimeEnhancement-Windows.zip` — опциональный portable archive.

Linux:

- `release/linux/AnimeEnhancement-Linux.tar.gz`.

macOS:

- `release/macos/AnimeEnhancement-macOS.zip`.
- Будущий `.dmg`, когда будет добавлена и проверена сборка DMG на macOS.
