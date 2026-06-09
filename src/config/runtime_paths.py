from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

APP_NAME = "AnimeEnhancement"
APP_ID = "anime-enhancement"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def project_root() -> Path:
    """Корень репозитория в dev-режиме."""
    return Path(__file__).resolve().parents[2]


def app_root() -> Path:
    """Корень приложения: repo root в dev, папка portable/.app в frozen."""
    if not is_frozen():
        return project_root()

    executable = Path(sys.executable).resolve()
    for parent in (executable.parent, *executable.parents):
        if parent.suffix == ".app":
            return parent
    return executable.parent


def _pyinstaller_meipass() -> Path | None:
    value = getattr(sys, "_MEIPASS", None)
    return Path(value).resolve() if value else None


def _repo_root_from_frozen_app() -> Path | None:
    """Dev-only: frozen exe from repo/dist should still use repo-local data."""
    root = app_root()
    for candidate in (root, *root.parents):
        if (candidate / "pyproject.toml").is_file() and (
            candidate / "src" / "config"
        ).is_dir():
            return candidate
    return None


def resource_path(relative: str | Path) -> Path:
    """Путь к bundled/dev ресурсу без зависимости от текущей рабочей директории."""
    relative_path = Path(relative)
    if relative_path.is_absolute():
        return relative_path

    if not is_frozen():
        return project_root() / relative_path

    candidates: list[Path] = []
    meipass = _pyinstaller_meipass()
    if meipass is not None:
        candidates.append(meipass / relative_path)

    root = app_root()
    candidates.extend(
        [
            root / relative_path,
            root / "Contents" / "Resources" / relative_path,
            root / "Contents" / "MacOS" / relative_path,
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def platform_key() -> str:
    system = platform.system()
    if system == "Windows":
        return "win"
    if system == "Darwin":
        return "macos"
    if system == "Linux":
        return "linux"
    return system.lower() or "unknown"


def executable_name(name: str) -> str:
    return f"{name}.exe" if platform.system() == "Windows" else name


_AI_TOOL_RELATIVE_DIRS = {
    "realesrgan-ncnn-vulkan": Path("src") / "utils" / "realesrgan",
    "waifu2x-ncnn-vulkan": Path("src") / "utils" / "waifu2x",
    "rife-ncnn-vulkan": Path("src") / "utils" / "rife",
}


def bundled_bin_path(name: str) -> Path:
    """Путь к app-local бинарнику для текущей ОС, если он включен в сборку."""
    base_name = name[:-4] if name.endswith(".exe") else name
    executable = executable_name(base_name)

    if base_name in _AI_TOOL_RELATIVE_DIRS:
        family = _AI_TOOL_RELATIVE_DIRS[base_name]
        family_name = family.name
        return resource_path(family / f"{family_name}-{platform_key()}" / executable)

    candidates = [
        Path("tools") / base_name / "bin" / executable,
        Path("tools") / base_name / executable,
        Path("tools") / "ffmpeg" / "bin" / executable,
        Path("tools") / "ffmpeg" / executable,
    ]
    for candidate in candidates:
        path = resource_path(candidate)
        if path.exists():
            return path
    return resource_path(candidates[0])


def user_data_dir() -> Path:
    override = os.getenv("ANIME_ENHANCEMENT_USER_DATA_DIR")
    if override:
        return Path(override).expanduser()

    system = platform.system()
    if system == "Windows":
        base = Path(os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / APP_NAME
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME

    base = Path(os.getenv("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / APP_ID


def user_config_dir() -> Path:
    override = os.getenv("ANIME_ENHANCEMENT_CONFIG_DIR")
    if override:
        return Path(override).expanduser()

    if is_frozen():
        repo_root = _repo_root_from_frozen_app()
        return (repo_root / "config") if repo_root else app_root() / "config"

    system = platform.system()
    if system == "Windows":
        return user_data_dir() / "config"
    if system == "Darwin":
        return user_data_dir() / "Config"

    base = Path(os.getenv("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / APP_ID


def default_data_dir() -> Path:
    override = os.getenv("ANIME_ENHANCEMENT_DATA_DIR")
    if override:
        return Path(override).expanduser()
    if is_frozen():
        repo_root = _repo_root_from_frozen_app()
        return (repo_root / "data") if repo_root else app_root() / "data"
    return project_root() / "data"


def profiles_dir() -> Path:
    if is_frozen():
        repo_root = _repo_root_from_frozen_app()
        return (repo_root / "profiles") if repo_root else app_root() / "profiles"
    return project_root() / "profiles"


def logs_parent_dir() -> Path:
    if is_frozen():
        return _repo_root_from_frozen_app() or app_root()
    return project_root()
