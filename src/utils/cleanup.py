from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from src.config.runtime_paths import (
    app_root,
    default_data_dir,
    logs_parent_dir,
    profiles_dir,
    project_root,
    resource_path,
)
from src.utils.logger import logger

PathLike = str | os.PathLike[str]


@dataclass(slots=True)
class CleanupResult:
    path: Path
    reason: str
    deleted: bool = False
    skipped: bool = False
    message: str = ""
    files_deleted: int = 0
    dirs_deleted: int = 0
    bytes_freed: int = 0
    stats_truncated: bool = False


@dataclass(slots=True)
class CleanupSummary:
    reason: str
    results: list[CleanupResult] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""

    @property
    def files_deleted(self) -> int:
        return sum(result.files_deleted for result in self.results)

    @property
    def dirs_deleted(self) -> int:
        return sum(result.dirs_deleted for result in self.results)

    @property
    def bytes_freed(self) -> int:
        return sum(result.bytes_freed for result in self.results)

    @property
    def deleted_paths(self) -> int:
        return sum(1 for result in self.results if result.deleted)


@dataclass(slots=True)
class _PathStats:
    files: int = 0
    dirs: int = 0
    bytes_size: int = 0
    truncated: bool = False


_TEMP_DIR_NAMES = (
    "audio",
    "tmp_video",
    "video_batches",
    "default_frame_batches",
    "denoised_frame_batches",
    "upscaled_frame_batches",
    "interpolated_frame_batches",
)
_DIAGNOSTIC_PARTS = {"diagnostic", "diagnostics", "diagnose", "diagnostics_artifacts"}


def cleanup_path(
    path: PathLike,
    reason: str,
    dry_run: bool = False,
    *,
    allowed_roots: Sequence[PathLike] | None = None,
    allow_outside_data_dir: bool = False,
    expected_type: str = "any",
) -> CleanupResult:
    target = Path(path).expanduser()
    result = CleanupResult(path=target, reason=reason)

    if not str(path).strip():
        result.skipped = True
        result.message = "пустой путь"
        logger.warning(f"Пропуск удаления: пустой путь. Причина запроса: {reason}")
        return result

    if not target.exists() and not target.is_symlink():
        result.skipped = True
        result.message = "путь не найден"
        logger.debug(f"Пропуск удаления: путь не найден: {target}")
        return result

    resolved = _resolve(target)
    safety_error = _get_safety_error(
        resolved,
        allowed_roots=allowed_roots,
        allow_outside_data_dir=allow_outside_data_dir,
    )
    if safety_error:
        result.skipped = True
        result.message = safety_error
        logger.warning(
            f"Пропуск удаления: {target}. Причина: {safety_error}. "
            f"Запрос: {reason}"
        )
        return result

    if expected_type == "file" and not (target.is_file() or target.is_symlink()):
        result.skipped = True
        result.message = "ожидался файл"
        logger.warning(f"Пропуск удаления: {target}. Ожидался файл.")
        return result
    if expected_type == "dir" and not target.is_dir():
        result.skipped = True
        result.message = "ожидалась директория"
        logger.warning(f"Пропуск удаления: {target}. Ожидалась директория.")
        return result

    stats = _collect_path_stats(target)
    result.files_deleted = stats.files
    result.dirs_deleted = stats.dirs
    result.bytes_freed = stats.bytes_size
    result.stats_truncated = stats.truncated

    if dry_run:
        result.skipped = True
        result.message = "dry-run"
        logger.info(
            f"DRY-RUN очистки: {target} не удален. Причина: {reason}. "
            f"Потенциально освободится {format_size(stats.bytes_size)}"
        )
        return result

    start_time = time.time()
    try:
        if target.is_dir() and not target.is_symlink():
            logger.info(f"Начало удаления временной директории: {target}. {reason}")
            shutil.rmtree(target)
        else:
            logger.info(f"Удаление временного файла: {target}. {reason}")
            target.unlink()
    except FileNotFoundError:
        result.skipped = True
        result.message = "путь уже удален"
        logger.debug(f"Пропуск удаления: путь уже удален: {target}")
        return result
    except OSError as error:
        result.skipped = True
        result.message = str(error)
        logger.error(f"Не удалось удалить {target}: {error}")
        return result

    result.deleted = True
    elapsed = time.time() - start_time
    approx = "примерно " if stats.truncated else ""
    logger.info(
        f"Удалено {stats.files} файлов и {stats.dirs} директорий, "
        f"освобождено {approx}{format_size(stats.bytes_size)} "
        f"за {elapsed:.1f} сек. Причина: {reason}"
    )
    return result


def cleanup_many(
    paths: Iterable[PathLike],
    reason: str,
    dry_run: bool = False,
    *,
    allowed_roots: Sequence[PathLike] | None = None,
    allow_outside_data_dir: bool = False,
) -> CleanupSummary:
    summary = CleanupSummary(reason=reason)
    for path in paths:
        summary.results.append(
            cleanup_path(
                path,
                reason,
                dry_run=dry_run,
                allowed_roots=allowed_roots,
                allow_outside_data_dir=allow_outside_data_dir,
            )
        )

    if summary.deleted_paths:
        approx = (
            "примерно "
            if any(result.stats_truncated for result in summary.results)
            else ""
        )
        logger.info(
            f"Итог очистки: удалено путей {summary.deleted_paths}, "
            f"файлов {summary.files_deleted}, директорий {summary.dirs_deleted}, "
            f"освобождено {approx}{format_size(summary.bytes_freed)}. "
            f"Причина: {reason}"
        )
    return summary


def format_size(bytes_count: int) -> str:
    value = float(max(0, bytes_count))
    for unit in ("Б", "КБ", "МБ", "ГБ", "ТБ"):
        if value < 1024 or unit == "ТБ":
            return f"{value:.1f} {unit}" if unit != "Б" else f"{int(value)} {unit}"
        value /= 1024
    return f"{value:.1f} ТБ"


def verify_file_exists_and_non_empty(path: PathLike) -> bool:
    target = Path(path)
    try:
        if target.is_file() and target.stat().st_size > 0:
            return True
    except OSError as error:
        logger.warning(f"Не удалось проверить файл {target}: {error}")
        return False
    logger.warning(f"Файл отсутствует или пустой: {target}")
    return False


def verify_video_readable(
    path: PathLike,
    *,
    require_video: bool = True,
    require_audio: bool = False,
    min_duration: float | None = None,
) -> bool:
    target = Path(path)
    if not verify_file_exists_and_non_empty(target):
        return False

    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=codec_type,nb_frames,nb_read_frames",
        "-of",
        "json",
        str(target),
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        logger.warning(f"ffprobe не смог проверить видео {target}: {error}")
        return False

    if result.returncode != 0:
        logger.warning(
            f"Видео не прошло проверку ffprobe: {target}. {result.stderr.strip()}"
        )
        return False

    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as error:
        logger.warning(f"ffprobe вернул некорректный JSON для {target}: {error}")
        return False

    streams = payload.get("streams", [])
    stream_types = {stream.get("codec_type") for stream in streams}
    if require_video and "video" not in stream_types:
        logger.warning(f"Видео-поток не найден: {target}")
        return False
    if require_audio and "audio" not in stream_types:
        logger.warning(f"Аудио-поток не найден: {target}")
        return False

    if min_duration is not None:
        raw_duration = str(payload.get("format", {}).get("duration", "0"))
        try:
            duration = float(raw_duration)
        except ValueError:
            duration = 0.0
        if duration < min_duration:
            logger.warning(
                f"Длительность видео меньше ожидаемой: {target} "
                f"({duration:.3f} сек < {min_duration:.3f} сек)"
            )
            return False

    return True


def verify_paths_exist_and_non_empty(
    paths: Iterable[PathLike],
    *,
    file_pattern: str | None = None,
) -> bool:
    for path in paths:
        target = Path(path)
        if target.is_dir():
            pattern = file_pattern or "*"
            if not any(
                child.is_file() and _safe_file_size(child) > 0
                for child in target.glob(pattern)
            ):
                logger.warning(f"Директория не содержит готовых файлов: {target}")
                return False
        elif not verify_file_exists_and_non_empty(target):
            return False
    return True


def maybe_cleanup_after_stage(
    *,
    stage: str,
    paths: Iterable[PathLike],
    reason: str,
    keep_temp_files: bool,
    dry_run: bool = False,
    dependency_path: PathLike | None = None,
    dependency_paths: Iterable[PathLike] | None = None,
    dependency_is_video: bool = False,
    require_audio: bool = False,
    min_duration: float | None = None,
    file_pattern: str | None = None,
    allowed_roots: Sequence[PathLike] | None = None,
) -> CleanupSummary:
    if keep_temp_files:
        message = f"KEEP_TEMP_FILES=true: временные файлы сохранены ({stage})"
        logger.info(message)
        return CleanupSummary(reason=reason, skipped=True, skip_reason=message)

    if dependency_path is not None:
        dependency_ok = (
            verify_video_readable(
                dependency_path,
                require_audio=require_audio,
                min_duration=min_duration,
            )
            if dependency_is_video
            else verify_file_exists_and_non_empty(dependency_path)
        )
        if not dependency_ok:
            message = (
                f"{stage}: пропуск удаления, зависимый файл не прошел проверку: "
                f"{dependency_path}"
            )
            logger.warning(message)
            return CleanupSummary(reason=reason, skipped=True, skip_reason=message)

    if dependency_paths is not None and not verify_paths_exist_and_non_empty(
        dependency_paths,
        file_pattern=file_pattern,
    ):
        message = f"{stage}: пропуск удаления, файлы следующей стадии не прошли проверку"
        logger.warning(message)
        return CleanupSummary(reason=reason, skipped=True, skip_reason=message)

    logger.info(f"{stage}: {reason}")
    return cleanup_many(
        paths,
        reason=f"{stage}: {reason}",
        dry_run=dry_run,
        allowed_roots=allowed_roots,
    )


def default_cleanup_roots(data_root: PathLike | None = None) -> list[Path]:
    root = Path(data_root).expanduser() if data_root is not None else default_data_dir()
    return [root / name for name in _TEMP_DIR_NAMES]


def _collect_path_stats(path: Path, *, max_entries: int = 20_000) -> _PathStats:
    stats = _PathStats()
    if path.is_file() or path.is_symlink():
        stats.files = 1
        stats.bytes_size = _safe_file_size(path)
        return stats

    if not path.is_dir():
        return stats

    stats.dirs = 1
    entries_seen = 0
    for root, dirs, files in os.walk(path):
        stats.dirs += len(dirs)
        entries_seen += len(dirs) + len(files)
        root_path = Path(root)
        for filename in files:
            stats.files += 1
            stats.bytes_size += _safe_file_size(root_path / filename)
        if entries_seen > max_entries:
            stats.truncated = True
            break
    return stats


def _get_safety_error(
    path: Path,
    *,
    allowed_roots: Sequence[PathLike] | None,
    allow_outside_data_dir: bool,
) -> str:
    if _is_dangerous_exact_path(path):
        return "опасный системный путь"

    if any(part.lower() in _DIAGNOSTIC_PARTS for part in path.parts):
        return "diagnostics-директории не удаляются автоматически"

    protected_subtree = _matched_protected_subtree(path)
    if protected_subtree is not None:
        return f"путь находится в защищенной области: {protected_subtree}"

    if allow_outside_data_dir:
        return ""

    roots = [
        _resolve(Path(root).expanduser())
        for root in (allowed_roots if allowed_roots is not None else default_cleanup_roots())
    ]
    if not any(path != root and path.is_relative_to(root) for root in roots):
        return "путь вне разрешенных временных директорий data"
    return ""


def _is_dangerous_exact_path(path: Path) -> bool:
    anchor = Path(path.anchor) if path.anchor else None
    exact_protected = {
        _resolve(Path.home()),
        _resolve(project_root()),
        _resolve(app_root()),
        _resolve(default_data_dir()),
    }
    if anchor is not None:
        exact_protected.add(_resolve(anchor))
    return path in exact_protected


def _matched_protected_subtree(path: Path) -> Path | None:
    data_root = default_data_dir()
    protected = [
        profiles_dir(),
        logs_parent_dir() / "logs",
        resource_path("assets"),
        resource_path("tools"),
        resource_path("src/utils"),
        data_root / "input_video",
        data_root / "output_video",
    ]
    for candidate in protected:
        resolved = _resolve(candidate)
        if path == resolved or path.is_relative_to(resolved):
            return resolved
    return None


def _resolve(path: Path) -> Path:
    try:
        return path.resolve(strict=False)
    except OSError:
        return path.absolute()


def _safe_file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0
