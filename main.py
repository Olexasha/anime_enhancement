from __future__ import annotations

import argparse
import asyncio
import json
import multiprocessing
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from src.config.dependency_checker import check_environment, format_report, has_errors
from src.config.pipeline_config import PROJECT_ROOT, PipelineConfig

GUI_PROGRESS_PREFIX = "__GUI_PROGRESS__"


def configure_text_output() -> None:
    """Принудительно пишет stdout/stderr в UTF-8 для GUI/QProcess на Windows."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


configure_text_output()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Улучшение аниме-видео через ffmpeg, RealESRGAN, waifu2x и RIFE."
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Путь к JSON-профилю настроек.",
    )
    parser.add_argument(
        "--check-environment",
        action="store_true",
        help="Проверить окружение и завершить работу без обработки видео.",
    )
    parser.add_argument(
        "--print-effective-config",
        action="store_true",
        help="Вывести итоговую конфигурацию JSON и завершить работу без обработки видео.",
    )
    parser.add_argument(
        "--skip-environment-check",
        action="store_true",
        help="Не выполнять проверку ffmpeg и AI-утилит перед обработкой.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Проверить профиль, входной файл и окружение без запуска обработки.",
    )
    return parser.parse_args(argv)


def initialize_multiprocessing() -> None:
    """Обслуживает служебный запуск worker-процессов в PyInstaller-сборке."""
    multiprocessing.freeze_support()


def load_runtime_config(config_path: Path | None) -> PipelineConfig:
    config = (
        PipelineConfig.from_json(config_path)
        if config_path
        else PipelineConfig.from_env()
    )
    errors = config.validate(require_input_exists=False)
    if errors:
        joined = "\n".join(f"- {error}" for error in errors)
        raise ValueError(f"Некорректная конфигурация:\n{joined}")
    config.apply_to_environment()
    return config


def print_effective_config(config: PipelineConfig) -> None:
    print(json.dumps(config.to_json_payload(), indent=2, ensure_ascii=False))


def emit_gui_progress(value: int, status: str) -> None:
    if os.getenv("ANIME_ENHANCEMENT_GUI_PROGRESS") != "1":
        return
    safe_value = max(0, min(100, int(value)))
    safe_status = status.replace("\n", " ").replace("|", "/")
    print(f"{GUI_PROGRESS_PREFIX}|{safe_value}|{safe_status}", flush=True)


@dataclass(frozen=True)
class ProgressWorkCosts:
    prepare_fixed: float = 30.0
    final_merge_fixed: float = 45.0
    audio_fixed: float = 35.0
    cleanup_fixed: float = 10.0
    done_fixed: float = 1.0
    extract_per_source_frame: float = 0.20
    denoise_per_source_frame: float = 0.80
    upscale_per_source_frame: float = 4.00
    interpolate_per_output_frame: float = 3.00
    short_video_per_window: float = 45.0


DEFAULT_PROGRESS_WORK_COSTS = ProgressWorkCosts()


class PipelineProgress:
    def __init__(
        self,
        *,
        enable_denoise: bool,
        enable_interpolation: bool,
        video_total_frames: int = 1,
        start_batch: int = 1,
        end_batch: int = 1,
        batch_size: int = 1000,
        total_windows: int = 1,
        frames_multiply_factor: int = 1,
        costs: ProgressWorkCosts | None = None,
    ) -> None:
        self.enable_denoise = enable_denoise
        self.enable_interpolation = enable_interpolation
        self.video_total_frames = max(1, int(video_total_frames))
        self.start_batch = max(1, int(start_batch))
        self.end_batch = max(self.start_batch, int(end_batch))
        self.batch_size = max(1, int(batch_size))
        self.total_windows = max(1, int(total_windows))
        self.frames_multiply_factor = (
            max(1, int(frames_multiply_factor)) if enable_interpolation else 1
        )
        self.costs = costs or DEFAULT_PROGRESS_WORK_COSTS
        self.total_source_frames = max(
            1,
            processed_source_frames(
                self.video_total_frames,
                self.start_batch,
                self.end_batch,
                self.batch_size,
            ),
        )
        self.total_interpolated_frames = (
            self.total_source_frames * self.frames_multiply_factor
        )
        self.work_totals = self._build_work_totals()
        self.work_done = dict.fromkeys(self.work_totals, 0.0)
        self._last_value = 0

    def _build_work_totals(self) -> dict[str, float]:
        totals = {
            "prepare": self.costs.prepare_fixed,
            "extract": self.total_source_frames * self.costs.extract_per_source_frame,
            "upscale": self.total_source_frames * self.costs.upscale_per_source_frame,
            "short_video": self.total_windows * self.costs.short_video_per_window,
            "final_merge": self.costs.final_merge_fixed,
            "audio": self.costs.audio_fixed,
            "cleanup": self.costs.cleanup_fixed,
            "done": self.costs.done_fixed,
        }
        if self.enable_denoise:
            totals["denoise"] = (
                self.total_source_frames * self.costs.denoise_per_source_frame
            )
        if self.enable_interpolation:
            totals["interpolate"] = (
                self.total_interpolated_frames * self.costs.interpolate_per_output_frame
            )
        return {stage: max(0.001, total) for stage, total in totals.items()}

    @property
    def total_work(self) -> float:
        return sum(self.work_totals.values())

    def value(self) -> int:
        progress = sum(self.work_done.values()) * 100 / max(self.total_work, 0.001)
        complete = all(
            self.work_done[stage] >= self.work_totals[stage]
            for stage in self.work_totals
        )
        upper_bound = 100 if complete else 99
        self._last_value = max(
            self._last_value, max(0, min(upper_bound, round(progress)))
        )
        return self._last_value

    def emit_status(self, status: str) -> None:
        overall = self.value()
        emit_gui_progress(overall, f"{status}; Общий прогресс: {overall}%")

    def update_stage(
        self,
        stage: str,
        *,
        done_units: float,
        total_units: float,
        status: str,
    ) -> int:
        if stage not in self.work_totals:
            self.emit_status(status)
            return self._last_value
        ratio = max(0.0, min(1.0, done_units / max(total_units, 0.001)))
        self.work_done[stage] = max(
            self.work_done[stage],
            self.work_totals[stage] * ratio,
        )
        self.emit_status(status)
        return self._last_value

    def update_frame_stage(
        self,
        stage: str,
        *,
        done_frames: float,
        status: str,
    ) -> int:
        total_frames = (
            self.total_interpolated_frames
            if stage == "interpolate"
            else self.total_source_frames
        )
        return self.update_stage(
            stage,
            done_units=done_frames,
            total_units=total_frames,
            status=status,
        )

    def update_short_videos_done(self, done_windows: int, status: str) -> int:
        return self.update_stage(
            "short_video",
            done_units=done_windows,
            total_units=self.total_windows,
            status=status,
        )

    def mark_fixed_step_done(self, step: str, status: str) -> int:
        if step in self.work_totals:
            self.work_done[step] = self.work_totals[step]
        self.emit_status(status)
        return self._last_value

    def source_frames_before_batch(self, batch_num: int) -> int:
        previous_end = min(batch_num - 1, self.end_batch)
        if previous_end < self.start_batch:
            return 0
        return processed_source_frames(
            self.video_total_frames,
            self.start_batch,
            previous_end,
            self.batch_size,
        )

    def source_frames_for_batches(self, batch_start: int, batch_end: int) -> int:
        clamped_start = max(self.start_batch, batch_start)
        clamped_end = min(self.end_batch, batch_end)
        if clamped_end < clamped_start:
            return 0
        return processed_source_frames(
            self.video_total_frames,
            clamped_start,
            clamped_end,
            self.batch_size,
        )

    def output_frames_before_batch(self, batch_num: int) -> int:
        return self.source_frames_before_batch(batch_num) * self.frames_multiply_factor

    def output_frames_for_batches(self, batch_start: int, batch_end: int) -> int:
        return (
            self.source_frames_for_batches(batch_start, batch_end)
            * self.frames_multiply_factor
        )

    def debug_summary(self, *, total_batches: int) -> str:
        interpolation_work = self.work_totals.get("interpolate", 0.0)
        lines = [
            "Progress model:",
            f"\ttotal_source_frames: {self.total_source_frames}",
            f"\ttotal_batches: {total_batches}",
            f"\ttotal_short_video_windows: {self.total_windows}",
            f"\tdenoise_enabled: {self.enable_denoise}",
            f"\tinterpolation_enabled: {self.enable_interpolation}",
            f"\texpected_interpolated_frames: {self.total_interpolated_frames if self.enable_interpolation else 0}",
            f"\texpected_interpolation_work_units: {interpolation_work:.2f}",
            f"\ttotal_work_units: {self.total_work:.2f}",
            "\twork_totals: "
            + ", ".join(
                f"{stage}={units:.2f}" for stage, units in self.work_totals.items()
            ),
            "\tcosts: "
            + ", ".join(
                f"{name}={value}" for name, value in self.costs.__dict__.items()
            ),
        ]
        return "\n".join(lines)


@dataclass(slots=True)
class CleanupTotals:
    deleted_paths: int = 0
    files_deleted: int = 0
    dirs_deleted: int = 0
    bytes_freed: int = 0

    def add(self, summary: Any | None) -> None:
        if summary is None:
            return
        if hasattr(summary, "deleted_paths"):
            self.deleted_paths += int(getattr(summary, "deleted_paths", 0))
        elif getattr(summary, "deleted", False):
            self.deleted_paths += 1
        self.files_deleted += int(getattr(summary, "files_deleted", 0))
        self.dirs_deleted += int(getattr(summary, "dirs_deleted", 0))
        self.bytes_freed += int(getattr(summary, "bytes_freed", 0))

    def add_many(self, summaries: list[Any] | tuple[Any, ...] | None) -> None:
        if not summaries:
            return
        for summary in summaries:
            self.add(summary)


def format_duration(value: float | timedelta) -> str:
    seconds = value.total_seconds() if isinstance(value, timedelta) else float(value)
    total_seconds = max(0, int(round(seconds)))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def format_size_ru(bytes_count: int) -> str:
    value = float(max(0, bytes_count))
    for unit in ("Б", "КБ", "МБ", "ГБ", "ТБ"):
        if value < 1024 or unit == "ТБ":
            return f"{value:.1f} {unit}" if unit != "Б" else f"{int(value)} {unit}"
        value /= 1024
    return f"{value:.1f} ТБ"


def processed_source_frames(
    total_frames: int,
    start_batch: int,
    end_batch: int,
    batch_size: int,
) -> int:
    start_frame = (start_batch - 1) * batch_size + 1
    end_frame = min(end_batch * batch_size, total_frames)
    if start_frame > total_frames:
        return 0
    return max(0, end_frame - start_frame + 1)


def print_header(title: str) -> None:
    from src.utils.logger import logger

    logger.info("=" * 50)
    logger.info(title.upper().center(50))


def print_bottom(title: str) -> None:
    from src.utils.logger import logger

    logger.info(title.upper().center(50))
    logger.info(f"{'=' * 50}\n")


async def clean_up(audio: Any) -> list[Any]:
    from src.config import settings
    from src.utils.cleanup import cleanup_many
    from src.utils.logger import logger

    if settings.KEEP_TEMP_FILES:
        logger.info("Очистка временных файлов пропущена: KEEP_TEMP_FILES=true")
        return []

    logger.info("Предварительная safe-очистка старых временных файлов")
    cleanup_summaries: list[Any] = []
    cleanup_paths = list(
        _existing_temp_children(
            [
                settings.INPUT_BATCHES_DIR,
                settings.DENOISED_BATCHES_DIR,
                settings.UPSCALED_BATCHES_DIR,
                settings.INTERPOLATED_BATCHES_DIR,
                settings.BATCH_VIDEO_PATH,
                settings.TMP_VIDEO_PATH,
            ]
        )
    )
    audio_cleanup = await audio.delete_audio_if_exists()
    if audio_cleanup is not None:
        cleanup_summaries.append(audio_cleanup)
    if cleanup_paths:
        cleanup_summaries.append(
            await asyncio.to_thread(
                cleanup_many,
                cleanup_paths,
                "предварительная очистка старых временных video-файлов",
            )
        )
    logger.debug("Временные файлы успешно удалены")
    return cleanup_summaries


def _existing_temp_children(directories: list[str]) -> list[Path]:
    children: list[Path] = []
    for directory in directories:
        path = Path(directory)
        if not path.exists():
            continue
        children.extend(child for child in path.iterdir() if child.name != ".gitkeep")
    return children


def choose_batch_window_size(
    process_threads: int,
    *,
    enable_interpolation: bool,
) -> int:
    """
    Подбирает размер общего окна обработки для баланса диска и скорости.

    Окно не уменьшается из-за RIFE: upscale должен сохранять полную
    параллельность, а тяжелая интерполяция ограничивается отдельными чанками.
    """
    _ = enable_interpolation
    return max(1, process_threads)


def calculate_interpolation_workers(process_threads: int) -> int:
    """Считает число параллельных RIFE-процессов для текущего окна."""
    return max(1, max(1, process_threads) // 3)


def calculate_short_video_windows(
    start_batch: int,
    end_batch: int,
    window_size: int,
) -> int:
    if end_batch < start_batch:
        return 0
    return ((end_batch - start_batch) // max(1, window_size)) + 1


def calculate_batches(total_frames: int | None = None) -> int:
    from src.config import settings
    from src.frames.frames_helpers import calculate_total_batches
    from src.utils.logger import logger

    if total_frames is not None:
        detected_batches = calculate_total_batches(
            total_frames,
            settings.FRAMES_PER_BATCH,
        )
        if settings.END_BATCH_TO_IMPROVE == 0:
            logger.debug(f"Автоопределение количества батчей: {detected_batches}")
            return detected_batches
        configured_end = min(settings.END_BATCH_TO_IMPROVE, detected_batches)
        logger.debug(
            f"Использовано фиксированное количество батчей: {configured_end} "
            f"(доступно: {detected_batches})"
        )
        return configured_end

    if settings.END_BATCH_TO_IMPROVE == 0:
        batch_name_pattern = re.compile(r"batch_(\d+)")
        batch_count = len(
            [
                batch
                for batch in os.listdir(settings.INPUT_BATCHES_DIR)
                if batch_name_pattern.match(batch)
            ]
        )
        logger.debug(f"Автоопределение количества батчей: {batch_count}")
        return batch_count

    logger.debug(
        f"Использовано фиксированное количество батчей: {settings.END_BATCH_TO_IMPROVE}"
    )
    return settings.END_BATCH_TO_IMPROVE


async def process_batches(
    threads: int,
    ai_threads: str,
    video: Any,
    ai_waifu2x_path: str,
    ai_realesrgan_path: str,
    ai_rife_path: str,
    start_batch: int,
    end_batch_to_improve: int,
    progress: PipelineProgress,
    progress_start_batch: int | None = None,
    progress_end_batch: int | None = None,
) -> list[Any]:
    from src.config import settings
    from src.frames.improve import ProcessingType, improve_batches
    from src.utils.cleanup import maybe_cleanup_after_stage
    from src.utils.logger import logger

    end_batch = 0
    first_batch = progress_start_batch or start_batch
    last_batch = progress_end_batch or end_batch_to_improve
    total_batches = max(1, last_batch - first_batch + 1)
    cleanup_summaries: list[Any] = []

    def emit_batch_progress(
        stage: str,
        display_name: str,
        batch_start: int,
        batch_end: int,
        local_percent: float,
        meta: Any | None = None,
    ) -> None:
        current_total = (
            progress.output_frames_for_batches(batch_start, batch_end)
            if stage == "interpolate"
            else progress.source_frames_for_batches(batch_start, batch_end)
        )
        frames_before = (
            progress.output_frames_before_batch(batch_start)
            if stage == "interpolate"
            else progress.source_frames_before_batch(batch_start)
        )
        if meta is not None and meta.processed_frames is not None:
            current_done = int(meta.processed_frames)
            local_percent = float(meta.percent)
        else:
            current_done = round(
                current_total * max(0.0, min(100.0, local_percent)) / 100
            )
        cumulative_done = frames_before + min(current_total, max(0, current_done))
        details = [
            f"Этап: {display_name}",
            f"Батчи: {batch_start}-{batch_end} из {end_batch_to_improve}",
            f"Прогресс этапа: {round(local_percent)}%",
        ]
        frame_label = "Выходные кадры" if stage == "interpolate" else "Кадры"
        if meta is not None:
            processed = getattr(meta, "processed_frames", None)
            total = getattr(meta, "total_frames", None)
            elapsed = getattr(meta, "elapsed_text", "")
            eta = getattr(meta, "eta_text", "")
            speed = getattr(meta, "speed_fps", None)
            if processed is not None and total is not None:
                details.append(f"{frame_label}: {processed}/{total}")
            if elapsed:
                details.append(f"Прошло: {elapsed}")
            if eta:
                details.append(f"Осталось: {eta}")
            if speed is not None:
                details.append(f"Скорость: {speed:.1f} FPS")
        progress.update_frame_stage(
            stage,
            done_frames=cumulative_done,
            status="; ".join(details),
        )

    async def cleanup_batch_dirs_after_stage(
        *,
        stage: str,
        source_dir: str,
        dependency_dir: str,
        batch_start: int,
        batch_end: int,
        reason: str,
    ) -> Any:
        source_paths = [
            Path(source_dir) / f"batch_{batch_num}"
            for batch_num in range(batch_start, batch_end + 1)
        ]
        dependency_paths = [
            Path(dependency_dir) / f"batch_{batch_num}"
            for batch_num in range(batch_start, batch_end + 1)
        ]
        return await asyncio.to_thread(
            maybe_cleanup_after_stage,
            stage=stage,
            paths=source_paths,
            reason=reason,
            keep_temp_files=settings.KEEP_TEMP_FILES,
            dependency_paths=dependency_paths,
            file_pattern=f"*.{settings.OUTPUT_IMAGE_FORMAT}",
        )

    while end_batch != end_batch_to_improve:
        end_batch = min(start_batch + threads - 1, end_batch_to_improve)
        logger.info(f"Обработка батчей с {start_batch} по {end_batch}")

        if settings.ENABLE_DENOISE:
            await improve_batches(
                ProcessingType.DENOISE,
                threads,
                ai_threads,
                ai_waifu2x_path,
                start_batch,
                end_batch,
                progress_callback=lambda percent,
                meta=None,
                batch_start=start_batch,
                batch_end=end_batch: emit_batch_progress(
                    "denoise", "Денойз", batch_start, batch_end, percent, meta
                ),
            )
            cleanup_summaries.append(
                await cleanup_batch_dirs_after_stage(
                    stage=f"Денойз батчей {start_batch}-{end_batch}",
                    source_dir=settings.INPUT_BATCHES_DIR,
                    dependency_dir=settings.DENOISED_BATCHES_DIR,
                    batch_start=start_batch,
                    batch_end=end_batch,
                    reason="денойз успешно создан, удаляем extracted frames батча",
                )
            )
            logger.success(
                f"Батчи {start_batch}-{end_batch} успешно обработаны денойзом"
            )
        else:
            logger.info("Денойз отключен: исходные PNG-кадры идут напрямую в апскейл")

        await improve_batches(
            ProcessingType.UPSCALE,
            threads,
            ai_threads,
            ai_realesrgan_path,
            start_batch,
            end_batch,
            progress_callback=lambda percent,
            meta=None,
            batch_start=start_batch,
            batch_end=end_batch: emit_batch_progress(
                "upscale", "Апскейл", batch_start, batch_end, percent, meta
            ),
        )
        cleanup_summaries.append(
            await cleanup_batch_dirs_after_stage(
                stage=f"Апскейл батчей {start_batch}-{end_batch}",
                source_dir=(
                    settings.DENOISED_BATCHES_DIR
                    if settings.ENABLE_DENOISE
                    else settings.INPUT_BATCHES_DIR
                ),
                dependency_dir=settings.UPSCALED_BATCHES_DIR,
                batch_start=start_batch,
                batch_end=end_batch,
                reason=(
                    "апскейл успешно создан, удаляем denoised frames батча"
                    if settings.ENABLE_DENOISE
                    else "апскейл успешно создан, удаляем extracted frames батча"
                ),
            )
        )
        logger.success(f"Батчи {start_batch}-{end_batch} успешно апскейлены")

        if settings.ENABLE_INTERPOLATION:
            interpolate_threads = calculate_interpolation_workers(threads)
            batch_nums = list(range(start_batch, end_batch + 1))

            for i in range(0, len(batch_nums), interpolate_threads):
                batches = batch_nums[i : i + interpolate_threads]
                logger.info(
                    f"Интерполяция батчей {batches} ({interpolate_threads} процессов)"
                )
                await improve_batches(
                    ProcessingType.INTERPOLATE,
                    interpolate_threads,
                    ai_threads,
                    ai_rife_path,
                    batches[0],
                    batches[-1],
                    progress_callback=lambda percent,
                    meta=None,
                    batch_start=batches[0],
                    batch_end=batches[-1]: emit_batch_progress(
                        "interpolate",
                        "RIFE",
                        batch_start,
                        batch_end,
                        percent,
                        meta,
                    ),
                )
                cleanup_summaries.append(
                    await cleanup_batch_dirs_after_stage(
                        stage=f"RIFE батчей {batches[0]}-{batches[-1]}",
                        source_dir=settings.UPSCALED_BATCHES_DIR,
                        dependency_dir=settings.INTERPOLATED_BATCHES_DIR,
                        batch_start=batches[0],
                        batch_end=batches[-1],
                        reason=(
                            "RIFE-кадры успешно созданы, удаляем upscaled frames батча"
                        ),
                    )
                )
            logger.success(f"Батчи {start_batch}-{end_batch} успешно интерполированы")
        else:
            logger.info(
                "Интерполяция отключена: видео собирается из апскейленных кадров"
            )

        batches_to_perform = [f"batch_{i}" for i in range(start_batch, end_batch + 1)]
        video.build_short_video(batches_to_perform)
        completed_batches = max(0, end_batch - first_batch + 1)
        ready_short_videos = _safe_short_video_queue_size(video)
        if ready_short_videos:
            progress.update_short_videos_done(
                ready_short_videos,
                f"Short-видео готово: {ready_short_videos}/{progress.total_windows}",
            )
        else:
            progress.emit_status(
                f"Short-видео поставлено в очередь: {completed_batches}/{total_batches} батчей"
            )
        start_batch += threads
    return cleanup_summaries


def _safe_short_video_queue_size(video: Any) -> int:
    queue = getattr(video, "video_queue", None)
    qsize = getattr(queue, "qsize", None)
    if qsize is None:
        return 0
    try:
        return max(0, int(qsize()))
    except (NotImplementedError, OSError):
        return 0


async def run_pipeline() -> None:
    from src.audio.audio_handling import AudioHandler
    from src.config import settings
    from src.config.comp_params import ComputerParams
    from src.frames.frames_helpers import (
        extract_frame_batches_range,
        get_fps_accurate,
        get_total_frame_count,
    )
    from src.utils.logger import logger
    from src.video.video_handling import VideoHandler

    start_time = datetime.now()
    cleanup_totals = CleanupTotals()
    emit_gui_progress(0, "Запуск улучшения видео")
    print_header("запуск улучшения видео")

    try:
        emit_gui_progress(0, "Проверка системы и путей к AI-утилитам")
        my_computer = ComputerParams()
        ai_realesrgan_path = my_computer.ai_realesrgan_path
        ai_waifu2x_path = my_computer.ai_waifu2x_path
        ai_rife_path = my_computer.ai_rife_path
        ai_threads, process_threads = my_computer.get_optimal_threads()

        logger.info(
            "Параметры системы:"
            f"\n\t{my_computer.hardware_report(ai_threads=ai_threads, process_threads=process_threads)}"
            f"\n\tПуть к нейронке денойза: {ai_waifu2x_path}"
            f"\n\tПуть к нейронке апскейла: {ai_realesrgan_path}"
            f"\n\tПуть к нейронке интерполяции: {ai_rife_path}"
        )
        if settings.KEEP_TEMP_FILES:
            logger.info("KEEP_TEMP_FILES=true: временные файлы будут сохранены")
        else:
            logger.info("Очистка временных файлов включена: режим safe")

        print_header("извлекаем кадры и готовим аудио")
        emit_gui_progress(0, "Подготовка кадров и аудио")
        audio = AudioHandler(
            threads=my_computer.safe_cpu_threads // 2,
            keep_temp_files=settings.KEEP_TEMP_FILES,
        )
        cleanup_totals.add_many(await clean_up(audio))

        asyncio.create_task(audio.extract_audio())
        total_frames = await asyncio.to_thread(
            get_total_frame_count,
            settings.ORIGINAL_VIDEO,
        )
        fps = await asyncio.to_thread(get_fps_accurate, settings.ORIGINAL_VIDEO)
        end_batch_to_improve = calculate_batches(total_frames)
        if settings.START_BATCH_TO_IMPROVE > end_batch_to_improve:
            raise ValueError(
                "START_BATCH_TO_IMPROVE больше количества доступных батчей: "
                f"{settings.START_BATCH_TO_IMPROVE} > {end_batch_to_improve}"
            )
        batch_window_size = choose_batch_window_size(
            process_threads,
            enable_interpolation=settings.ENABLE_INTERPOLATION,
        )
        expected_short_videos = calculate_short_video_windows(
            settings.START_BATCH_TO_IMPROVE,
            end_batch_to_improve,
            batch_window_size,
        )
        progress = PipelineProgress(
            enable_denoise=settings.ENABLE_DENOISE,
            enable_interpolation=settings.ENABLE_INTERPOLATION,
            video_total_frames=total_frames,
            start_batch=settings.START_BATCH_TO_IMPROVE,
            end_batch=end_batch_to_improve,
            batch_size=settings.FRAMES_PER_BATCH,
            total_windows=expected_short_videos,
            frames_multiply_factor=settings.FRAMES_MULTIPLY_FACTOR,
        )
        logger.debug(
            progress.debug_summary(
                total_batches=end_batch_to_improve - settings.START_BATCH_TO_IMPROVE + 1
            )
        )
        progress.mark_fixed_step_done("prepare", "Система и AI-утилиты проверены")
        logger.info(
            "Windowed pipeline:"
            f"\n\tВсего кадров: {total_frames}"
            f"\n\tВсего батчей для обработки: {end_batch_to_improve}"
            f"\n\tБатчей в одном окне/short: {batch_window_size}"
            "\n\tАктивных short-video builders: 2"
        )
        video = VideoHandler(fps=fps, max_short_video_builders=2)
        print_bottom("кадры и аудио подготовлены")
        progress.emit_status("Метаданные видео и аудио подготовлены")

        print_header("генерируем улучшенные короткие видео")
        progress.emit_status(f"Начало ИИ-обработки батчей: {end_batch_to_improve}")
        extracted_frames_done = 0
        for window_start in range(
            settings.START_BATCH_TO_IMPROVE,
            end_batch_to_improve + 1,
            batch_window_size,
        ):
            window_end = min(window_start + batch_window_size - 1, end_batch_to_improve)
            extracted_frames_done += extract_frame_batches_range(
                threads=my_computer.safe_cpu_threads // 2,
                start_batch=window_start,
                end_batch=window_end,
                video_path=settings.ORIGINAL_VIDEO,
                output_dir=settings.INPUT_BATCHES_DIR,
                batch_size=settings.FRAMES_PER_BATCH,
            )
            progress.update_frame_stage(
                "extract",
                done_frames=extracted_frames_done,
                status=(
                    f"Этап: Извлечение кадров; "
                    f"Окно: батчи {window_start}-{window_end} из {end_batch_to_improve}; "
                    f"Кадры: {extracted_frames_done}/{progress.total_source_frames}"
                ),
            )
            cleanup_totals.add_many(
                await process_batches(
                    process_threads,
                    ai_threads,
                    video,
                    ai_waifu2x_path,
                    ai_realesrgan_path,
                    ai_rife_path,
                    window_start,
                    window_end,
                    progress,
                    progress_start_batch=settings.START_BATCH_TO_IMPROVE,
                    progress_end_batch=end_batch_to_improve,
                )
            )
        print_bottom("улучшенные короткие видео сгенерированы")
        progress.emit_status("Все short-видео поставлены в очередь сборки")

        print_header("начало финальной сборки видео")
        progress.emit_status("Финальная сборка видео")
        total_short_videos = video.short_videos_requested
        if total_short_videos != expected_short_videos:
            logger.warning(
                f"Количество запрошенных short-видео отличается от ожидаемого: "
                f"{total_short_videos} != {expected_short_videos}"
            )

        def update_short_video_progress(done: int, total: int) -> None:
            progress.update_short_videos_done(
                done,
                f"Этап: Сборка short-видео; Готово: {done}/{total}",
            )

        final_merge = await video.build_final_video(
            total_short_videos,
            short_video_progress_callback=update_short_video_progress,
        )
        cleanup_totals.add_many(getattr(video, "cleanup_summaries", []))
        logger.success(f"Общее видео собрано: {final_merge}")
        progress.mark_fixed_step_done("final_merge", "Финальная сборка видео завершена")

        logger.info("Добавление аудиодорожки к финальному видео")
        progress.emit_status("Добавление аудиодорожки")
        audio.tmp_video_path = final_merge
        cleanup_totals.add(await audio.insert_audio())
        logger.success(f"Аудио добавлено к {settings.FINAL_VIDEO}")
        progress.mark_fixed_step_done("cleanup", "Очистка временных файлов завершена")
        progress.mark_fixed_step_done("audio", "Аудиодорожка добавлена")
        print_bottom("финальная сборка завершена")

        execution_time = datetime.now() - start_time
        elapsed_text = format_duration(execution_time)
        source_frames_done = processed_source_frames(
            total_frames,
            settings.START_BATCH_TO_IMPROVE,
            end_batch_to_improve,
            settings.FRAMES_PER_BATCH,
        )
        avg_speed = source_frames_done / max(execution_time.total_seconds(), 0.001)
        logger.success(f"Итоговое видео сохранено: {settings.FINAL_VIDEO}")
        logger.success(f"ГОТОВО: видео обработано за {elapsed_text}")
        logger.info(
            "Сводка обработки:"
            f"\n\tИсходное видео: {settings.ORIGINAL_VIDEO}"
            f"\n\tИтоговый файл: {settings.FINAL_VIDEO}"
            f"\n\tОбработано исходных кадров: {source_frames_done}"
            f"\n\tИтоговый FPS: {video.fps:.3f}"
            f"\n\tДлительность обработки: {elapsed_text}"
            f"\n\tСредняя скорость: {avg_speed:.2f} исходных кадров/сек"
            f"\n\tОчистка: удалено путей {cleanup_totals.deleted_paths}, "
            f"файлов {cleanup_totals.files_deleted}, "
            f"директорий {cleanup_totals.dirs_deleted}, "
            f"освобождено {format_size_ru(cleanup_totals.bytes_freed)}"
        )
        progress.mark_fixed_step_done(
            "done", f"ГОТОВО: видео обработано за {elapsed_text}"
        )
        print_bottom("улучшение видео завершено")
    except Exception as error:
        logger.critical(f"Критическая ошибка: {str(error)}")
        raise


def main(argv: list[str] | None = None) -> int:
    initialize_multiprocessing()
    args = parse_args(argv)
    try:
        config = load_runtime_config(args.config)
        if args.print_effective_config:
            print_effective_config(config)
            return 0

        if args.check_environment:
            checks = check_environment(config, PROJECT_ROOT)
            print(format_report(checks))
            return 1 if has_errors(checks) else 0

        input_errors = config.validate(require_input_exists=True)
        if input_errors:
            raise ValueError(
                "Некорректная конфигурация:\n"
                + "\n".join(f"- {error}" for error in input_errors)
            )

        if not args.skip_environment_check:
            checks = check_environment(config, PROJECT_ROOT)
            if has_errors(checks):
                raise RuntimeError(
                    "Проверка окружения не пройдена:\n" + format_report(checks)
                )

        if args.dry_run:
            print(
                "Профиль, входной файл и окружение проверены. Обработка не запускалась."
            )
            return 0

        asyncio.run(run_pipeline())
        return 0
    except Exception as error:
        print(f"Критическая ошибка: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
