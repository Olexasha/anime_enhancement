import importlib
import shutil
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

FFMPEG_COMMAND = "ffmpeg"
FFPROBE_COMMAND = "ffprobe"


def reload_project_modules(*module_names: str):
    """Перезагружает модули, которые читают настройки при импорте."""
    modules = []
    for module_name in module_names:
        module = importlib.import_module(module_name)
        modules.append(importlib.reload(module))
    return modules


def configure_test_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Изолирует файловые настройки проекта внутри временной директории pytest."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANIME_ENHANCEMENT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ORIGINAL_VIDEO", str(tmp_path / "original.mp4"))
    monkeypatch.setenv("FINAL_VIDEO", str(tmp_path / "final.mp4"))
    monkeypatch.setenv("OUTPUT_IMAGE_FORMAT", "png")
    monkeypatch.setenv("ENABLE_DENOISE", "false")
    monkeypatch.setenv("ENABLE_INTERPOLATION", "false")
    monkeypatch.setenv("UPSCALE_FACTOR", "3")
    monkeypatch.setenv("VIDEO_ENCODER", "libx264")
    monkeypatch.setenv("VIDEO_CRF", "23")
    monkeypatch.setenv("VIDEO_PRESET", "ultrafast")
    monkeypatch.setenv("VIDEO_PIX_FMT", "yuv420p")
    monkeypatch.setenv("FRAMES_MULTIPLY_FACTOR", "2")
    monkeypatch.setenv("KEEP_TEMP_FILES", "false")


def _is_command_available(command: str) -> bool:
    """Проверяет наличие команды в PATH без передачи PathLike в shutil.which."""
    return shutil.which(str(command)) is not None


def require_video_tools() -> None:
    """Пропускает видео-тесты, если локальное окружение не готово."""
    if not _is_command_available(FFMPEG_COMMAND) or not _is_command_available(
        FFPROBE_COMMAND
    ):
        pytest.skip("Для теста нужны ffmpeg и ffprobe в PATH")

    try:
        import cv2  # noqa: F401
        import numpy  # noqa: F401
    except ImportError as error:
        pytest.skip(f"Для теста нужны opencv-python и numpy: {error}")
