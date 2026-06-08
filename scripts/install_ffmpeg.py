from __future__ import annotations

import argparse
import platform
import shutil
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = PROJECT_ROOT / "tools"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Проверка и app-local установка FFmpeg."
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Только вывести отчет, без установки.",
    )
    args = parser.parse_args()

    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if ffmpeg and ffprobe:
        print(f"FFmpeg найден: {ffmpeg}")
        print(f"ffprobe найден: {ffprobe}")
        return 0

    print("FFmpeg или ffprobe не найден в PATH.")
    if args.report_only:
        return 1

    system = platform.system()
    if system == "Windows":
        return install_windows_local()
    if system == "Linux":
        print(
            "Linux: установите FFmpeg через пакетный менеджер, например: sudo apt install ffmpeg"
        )
        return 1
    if system == "Darwin":
        print("macOS: установите FFmpeg через Homebrew: brew install ffmpeg")
        return 1
    print(f"Неподдерживаемая ОС для автоустановки FFmpeg: {system}")
    return 1


def install_windows_local() -> int:
    archive = PROJECT_ROOT / "src" / "utils" / "ffmpeg_win.zip"
    target = TOOLS_DIR / "ffmpeg"
    if not archive.exists():
        print(f"Локальный архив FFmpeg не найден: {archive}")
        print(
            "Установите FFmpeg вручную или положите ffmpeg.exe/ffprobe.exe в tools/ffmpeg/bin."
        )
        return 1

    target.mkdir(parents=True, exist_ok=True)
    print(f"Распаковка FFmpeg в {target}")
    with zipfile.ZipFile(archive) as zip_file:
        zip_file.extractall(target)

    bin_dir = find_ffmpeg_bin(target)
    if not bin_dir:
        print("После распаковки ffmpeg.exe и ffprobe.exe не найдены.")
        return 1

    normalized_bin = target / "bin"
    normalized_bin.mkdir(parents=True, exist_ok=True)
    for exe in ("ffmpeg.exe", "ffprobe.exe"):
        source = bin_dir / exe
        if source.exists():
            shutil.copy2(source, normalized_bin / exe)
    print(f"FFmpeg установлен app-local: {normalized_bin}")
    print("GUI и CLI добавят эту папку в PATH процесса автоматически.")
    return 0


def find_ffmpeg_bin(root: Path) -> Path | None:
    for ffmpeg in root.rglob("ffmpeg.exe"):
        candidate = ffmpeg.parent
        if (candidate / "ffprobe.exe").exists():
            return candidate
    return None


if __name__ == "__main__":
    raise SystemExit(main())
