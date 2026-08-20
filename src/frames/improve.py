import asyncio
import inspect
import os
import shutil
import subprocess
import time
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import cv2

from src.config.settings import (
    DENOISE_FACTOR,
    DENOISED_BATCHES_DIR,
    ENABLE_DENOISE,
    ENABLE_SPATIAL_TTA_MODE,
    ENABLE_TEMPORAL_TTA_MODE,
    ENABLE_UHD_MODE,
    FRAMES_MULTIPLY_FACTOR,
    INPUT_BATCHES_DIR,
    INTERPOLATED_BATCHES_DIR,
    KEEP_TEMP_FILES,
    OUTPUT_IMAGE_FORMAT,
    REALESRGAN_MODEL_DIR,
    REALESRGAN_MODEL_NAME,
    RIFE_MODEL_DIR,
    SCENE_CUT_DEBUG,
    SCENE_CUT_DETECTION_METHOD,
    SCENE_CUT_GUARD_ENABLED,
    SCENE_CUT_MIN_SCENE_FRAMES,
    SCENE_CUT_THRESHOLD,
    STATIC_SCENE_GUARD_ENABLED,
    STATIC_SCENE_MIN_DURATION_SECONDS,
    TIME_STEP,
    TMP_VIDEO_PATH,
    UPSCALE_FACTOR,
    UPSCALED_BATCHES_DIR,
    WAIFU2X_MODEL_DIR,
    WAIFU2X_UPSCALE_FACTOR,
)
from src.files.file_actions import create_dir
from src.frames.frames_helpers import count_frames_in_certain_batches
from src.frames.scene_cut_guard import (
    GuardSegment,
    SceneCutPlan,
    SceneCutScanResult,
    StaticSceneRun,
    build_guard_segments,
    build_scene_cut_plans,
    build_scene_segments,
    build_static_frame_map,
    calculate_static_scene_min_run_frames,
    list_batch_frames,
    write_scene_cut_debug,
)
from src.utils.logger import logger
from src.video.video_helpers import sort_frame_paths

MAX_RETRIES = 3  # макс количество попыток при неудаче на обработке фреймов
RETRY_DELAY = 2  # задержка между попытками в сек
STATIC_RIFE_MIN_SAVED_MEGAPIXEL_FRAMES_PER_EXTRA_PROCESS = 12.0


class ProcessingType(Enum):
    """Типы обработки фреймов"""

    UPSCALE = "upscale"
    DENOISE = "denoise"
    INTERPOLATE = "interpolate"


@dataclass(frozen=True, slots=True)
class BatchImproveStats:
    source_frames: int
    ai_input_frames: int
    static_frames_skipped: int = 0
    interpolation_segments: int = 0
    rife_calls: int = 0
    optimization_bypassed: bool = False


# Конфигурация для каждого типа обработки
PROCESSING_CONFIG: dict[ProcessingType, dict[str, Any]] = {
    ProcessingType.DENOISE: {
        "input_dir": INPUT_BATCHES_DIR,
        "output_dir": DENOISED_BATCHES_DIR,
        "model_dir": WAIFU2X_MODEL_DIR,
        "scale_factor": WAIFU2X_UPSCALE_FACTOR,
        "denoise_factor": DENOISE_FACTOR,
        "display_name": "Денойз",
        "start_name": "денойза",
        "error_name": "денойзе",
    },
    ProcessingType.UPSCALE: {
        "input_dir": DENOISED_BATCHES_DIR if ENABLE_DENOISE else INPUT_BATCHES_DIR,
        "output_dir": UPSCALED_BATCHES_DIR,
        "model_dir": REALESRGAN_MODEL_DIR,
        "model_name": REALESRGAN_MODEL_NAME,
        "scale_factor": UPSCALE_FACTOR,
        "display_name": "Апскейл",
        "start_name": "апскейла",
        "error_name": "апскейле",
    },
    ProcessingType.INTERPOLATE: {
        "input_dir": UPSCALED_BATCHES_DIR,
        "output_dir": INTERPOLATED_BATCHES_DIR,
        "model_dir": RIFE_MODEL_DIR,
        "num_frame": FRAMES_MULTIPLY_FACTOR,
        "time_step": TIME_STEP,
        "display_name": "RIFE",
        "start_name": "интерполяции RIFE",
        "error_name": "интерполяции RIFE",
    },
}


@dataclass(frozen=True, slots=True)
class ProgressSnapshot:
    processed_frames: int
    total_frames: int
    percent: float
    elapsed_text: str
    eta_text: str
    speed_fps: float


class ProgressRateEstimator:
    def __init__(self, *, alpha: float = 0.25) -> None:
        self.alpha = alpha
        self.start_time = time.time()
        self.last_time = self.start_time
        self.last_count = 0
        self.smoothed_rate: float | None = None
        self.samples = 0

    def update(self, count: int, now: float) -> float:
        delta_count = max(0, count - self.last_count)
        delta_time = max(0.001, now - self.last_time)
        if delta_count > 0:
            instant_rate = delta_count / delta_time
            if self.smoothed_rate is None:
                self.smoothed_rate = instant_rate
            else:
                self.smoothed_rate = (
                    self.alpha * instant_rate + (1 - self.alpha) * self.smoothed_rate
                )
            self.samples += 1
            self.last_count = count
            self.last_time = now
        elapsed = max(0.001, now - self.start_time)
        return self.smoothed_rate if self.smoothed_rate is not None else count / elapsed

    def eta_text(self, *, total: int, count: int, percent: float, now: float) -> str:
        elapsed = now - self.start_time
        if elapsed < 3 or percent < 3 or self.samples < 2 or not self.smoothed_rate:
            return "рассчитывается..."
        remaining = max(0, total - count) / max(self.smoothed_rate, 0.001)
        return f"~{format_duration(remaining)}"


def format_duration(seconds: float) -> str:
    total_seconds = max(0, int(round(seconds)))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _call_progress_callback(
    progress_callback: Callable[..., None] | None,
    percent: float,
    snapshot: ProgressSnapshot,
) -> None:
    if progress_callback is None:
        return
    try:
        parameters = inspect.signature(progress_callback).parameters
        accepts_meta = (
            any(
                parameter.kind == inspect.Parameter.VAR_POSITIONAL
                for parameter in parameters.values()
            )
            or len(parameters) >= 2
        )
    except (TypeError, ValueError):
        accepts_meta = False
    if accepts_meta:
        progress_callback(percent, snapshot)
    else:
        progress_callback(percent)


def _rife_flags() -> list[str]:
    flags = []
    if ENABLE_UHD_MODE:
        flags.append("-u")
    if ENABLE_SPATIAL_TTA_MODE:
        flags.append("-x")
    if ENABLE_TEMPORAL_TTA_MODE:
        flags.append("-z")
    return flags


def _build_rife_command(
    *,
    ai_tool_path: str,
    ai_threads: str,
    input_dir: Path,
    output_dir: Path,
    frame_count: int,
) -> list[Any]:
    config = PROCESSING_CONFIG[ProcessingType.INTERPOLATE]
    command: list[Any] = [
        ai_tool_path,
        "-i",
        str(input_dir),
        "-o",
        output_dir,
        "-m",
        config["model_dir"],
        "-f",
        OUTPUT_IMAGE_FORMAT,
        "-j",
        ai_threads,
    ]
    if FRAMES_MULTIPLY_FACTOR > 2:
        command.extend(
            (
                "-n",
                str(config["num_frame"] * frame_count),
                "-s",
                str(config["time_step"]),
            )
        )
    command.extend(_rife_flags())
    return command


def _run_ai_command(
    command: list[Any],
    *,
    config: dict[str, Any],
    batch_num: int,
    max_retries: int,
    context: str = "",
) -> None:
    cmd_args = [str(arg) for arg in command]
    logger.debug(" ".join(cmd_args))

    context_suffix = f" ({context})" if context else ""
    for attempt in range(max_retries):
        try:
            logger.debug(
                f"Запуск {config['display_name'].lower()} батча {batch_num}{context_suffix} "
                f"с параметрами. Попытка: {attempt + 1}/{max_retries}"
            )
            subprocess.run(command, capture_output=True, text=True, check=True)
            return

        except subprocess.CalledProcessError as error:
            logger.error(
                f"Ошибка в батче {batch_num}{context_suffix} "
                f"(попытка {attempt + 1}): {error.stderr}"
            )
            if attempt < max_retries - 1:
                time.sleep(RETRY_DELAY)
            else:
                raise RuntimeError(
                    f"Не удалось обработать батч {batch_num} "
                    f"на этапе {config['display_name']} после {max_retries} попыток"
                ) from error

        except Exception as error:
            logger.error(
                f"Неожиданная ошибка в батче {batch_num}{context_suffix}: {str(error)}"
            )
            raise


def _link_or_copy_frame(source: str | Path, target: Path) -> None:
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def _replace_with_link_or_copy(source: str | Path, target: Path) -> None:
    if target.exists():
        target.unlink()
    _link_or_copy_frame(source, target)


def _clear_top_level_frames(directory: Path) -> None:
    for frame_path in directory.glob(f"*.{OUTPUT_IMAGE_FORMAT}"):
        frame_path.unlink()


def _materialize_static_frames(
    frame_path: str,
    source_frame_count: int,
    output_dir: Path,
    next_output_index: int,
) -> int:
    output_count = source_frame_count * max(1, FRAMES_MULTIPLY_FACTOR)
    for _ in range(output_count):
        target = output_dir / f"frame_{next_output_index:08d}.{OUTPUT_IMAGE_FORMAT}"
        _replace_with_link_or_copy(frame_path, target)
        next_output_index += 1
    return next_output_index


def _move_segment_outputs(
    segment_output_dir: Path,
    output_dir: Path,
    next_output_index: int,
) -> int:
    generated_frames = sort_frame_paths(
        [
            str(path)
            for path in segment_output_dir.iterdir()
            if path.is_file()
            and path.name.lower().endswith(f".{OUTPUT_IMAGE_FORMAT.lower()}")
        ]
    )
    if not generated_frames:
        raise RuntimeError(f"RIFE не создал кадры сегмента: {segment_output_dir}")

    for generated_frame in generated_frames:
        target = output_dir / f"frame_{next_output_index:08d}.{OUTPUT_IMAGE_FORMAT}"
        shutil.move(generated_frame, target)
        next_output_index += 1
    return next_output_index


def _prepare_static_stage_input(
    *,
    input_dir: Path,
    temp_input_dir: Path,
    batch_num: int,
    static_runs: tuple[StaticSceneRun, ...],
) -> tuple[Path, dict[str, str]]:
    frame_paths = list_batch_frames(
        input_dir.parent,
        batch_num,
        OUTPUT_IMAGE_FORMAT,
    )
    duplicate_map = build_static_frame_map(frame_paths, static_runs)
    if not duplicate_map:
        return input_dir, {}

    if temp_input_dir.exists():
        shutil.rmtree(temp_input_dir, ignore_errors=True)
    temp_input_dir.mkdir(parents=True, exist_ok=True)
    for frame_path in frame_paths:
        if frame_path in duplicate_map:
            continue
        _link_or_copy_frame(frame_path, temp_input_dir / Path(frame_path).name)
    return temp_input_dir, duplicate_map


def _materialize_static_stage_outputs(
    *,
    output_dir: Path,
    duplicate_map: dict[str, str],
) -> None:
    # Этот каталог дальше только читается; следующая стадия пишет результат отдельно.
    for duplicate_path, representative_path in duplicate_map.items():
        representative_output = output_dir / Path(representative_path).name
        if not representative_output.is_file():
            raise RuntimeError(
                "Static Scene Guard: AI-утилита не создала кадр-представитель "
                f"{representative_output}"
            )
        duplicate_output = output_dir / Path(duplicate_path).name
        _replace_with_link_or_copy(representative_output, duplicate_output)


def _build_profitable_interpolation_segments(
    frame_paths: list[str],
    scene_cut_plan: SceneCutPlan,
) -> tuple[list[GuardSegment], bool]:
    guarded_segments = build_guard_segments(
        frame_paths,
        scene_cut_plan.cuts,
        scene_cut_plan.static_runs,
    )
    if not scene_cut_plan.static_runs:
        return guarded_segments, False

    baseline_segments = build_scene_segments(frame_paths, scene_cut_plan.cuts)
    baseline_rife_calls = sum(
        len(segment.frame_paths) > 1 for segment in baseline_segments
    )
    guarded_rife_calls = sum(
        not segment.is_static and len(segment.frame_paths) > 1
        for segment in guarded_segments
    )
    extra_rife_calls = max(0, guarded_rife_calls - baseline_rife_calls)
    if extra_rife_calls == 0:
        return guarded_segments, False

    static_frames = sum(
        len(segment.frame_paths) for segment in guarded_segments if segment.is_static
    )
    first_frame = cv2.imread(frame_paths[0], cv2.IMREAD_GRAYSCALE)
    if first_frame is None:
        logger.warning(
            "Static Scene Guard: не удалось оценить разрешение; "
            "RIFE-оптимизация статичных серий пропущена"
        )
        return build_guard_segments(frame_paths, scene_cut_plan.cuts, ()), True

    saved_megapixel_frames = static_frames * first_frame.size / 1_000_000
    required_savings = (
        extra_rife_calls * STATIC_RIFE_MIN_SAVED_MEGAPIXEL_FRAMES_PER_EXTRA_PROCESS
    )
    if saved_megapixel_frames < required_savings:
        logger.debug(
            "Static Scene Guard: RIFE-оптимизация не окупит дополнительные "
            f"запуски модели ({saved_megapixel_frames:.1f} < "
            f"{required_savings:.1f} MP-кадров)"
        )
        return build_guard_segments(frame_paths, scene_cut_plan.cuts, ()), True
    return guarded_segments, False


def _improve_interpolation_batch_with_scene_cut_guard(
    *,
    ai_threads: str,
    ai_tool_path: str,
    batch_num: int,
    input_dir: Path,
    output_dir: Path,
    scene_cut_plan: SceneCutPlan,
    max_retries: int,
) -> BatchImproveStats:
    config = PROCESSING_CONFIG[ProcessingType.INTERPOLATE]
    frame_paths = list_batch_frames(
        input_dir.parent,
        batch_num,
        OUTPUT_IMAGE_FORMAT,
    )
    segments, optimization_bypassed = _build_profitable_interpolation_segments(
        frame_paths,
        scene_cut_plan,
    )
    if not segments:
        raise RuntimeError(f"Scene Cut Guard: нет кадров для batch_{batch_num}")

    static_frames_skipped = sum(
        len(segment.frame_paths) for segment in segments if segment.is_static
    )
    rife_calls = sum(
        not segment.is_static and len(segment.frame_paths) > 1 for segment in segments
    )
    ai_input_frames = sum(
        len(segment.frame_paths)
        for segment in segments
        if not segment.is_static and len(segment.frame_paths) > 1
    )
    logger.debug(
        f"Frame Guard: batch_{batch_num}: cut={len(scene_cut_plan.cuts)}, "
        f"static-сегментов={sum(segment.is_static for segment in segments)}, "
        f"всего сегментов={len(segments)}"
    )

    temp_root = output_dir.parent / f"_scene_cut_guard_batch_{batch_num}"
    if temp_root.exists():
        shutil.rmtree(temp_root, ignore_errors=True)
    temp_root.mkdir(parents=True, exist_ok=True)
    _clear_top_level_frames(output_dir)

    next_output_index = 1
    try:
        for segment_index, segment in enumerate(segments, start=1):
            segment_frames = list(segment.frame_paths)
            if segment.is_static or len(segment_frames) == 1:
                next_output_index = _materialize_static_frames(
                    segment_frames[0],
                    len(segment_frames),
                    output_dir,
                    next_output_index,
                )
                continue

            segment_input_dir = temp_root / f"scene_{segment_index:06d}_input"
            segment_output_dir = temp_root / f"scene_{segment_index:06d}_output"
            segment_input_dir.mkdir(parents=True, exist_ok=True)
            segment_output_dir.mkdir(parents=True, exist_ok=True)

            for local_index, source_frame in enumerate(segment_frames, start=1):
                target = (
                    segment_input_dir / f"frame_{local_index:08d}.{OUTPUT_IMAGE_FORMAT}"
                )
                _link_or_copy_frame(source_frame, target)

            command = _build_rife_command(
                ai_tool_path=ai_tool_path,
                ai_threads=ai_threads,
                input_dir=segment_input_dir,
                output_dir=segment_output_dir,
                frame_count=len(segment_frames),
            )
            _run_ai_command(
                command,
                config=config,
                batch_num=batch_num,
                max_retries=max_retries,
                context=(
                    f"scene {segment_index}/{len(segments)} "
                    f"{segment.start_frame}-{segment.end_frame}"
                ),
            )
            next_output_index = _move_segment_outputs(
                segment_output_dir,
                output_dir,
                next_output_index,
            )

        output_frames = next_output_index - 1
        expected_frames = len(frame_paths) * max(1, FRAMES_MULTIPLY_FACTOR)
        if output_frames != expected_frames:
            raise RuntimeError(
                f"Scene Cut Guard: batch_{batch_num} создал {output_frames} кадров, "
                f"ожидалось {expected_frames}"
            )
        return BatchImproveStats(
            source_frames=len(frame_paths),
            ai_input_frames=ai_input_frames,
            static_frames_skipped=static_frames_skipped,
            interpolation_segments=len(segments),
            rife_calls=rife_calls,
            optimization_bypassed=optimization_bypassed,
        )
    finally:
        if not KEEP_TEMP_FILES:
            shutil.rmtree(temp_root, ignore_errors=True)


def _improve_batch(
    processing_type: ProcessingType,
    ai_threads: str,
    ai_tool_path: str,
    batch_num: int,
    max_retries: int = MAX_RETRIES,
    scene_cut_plan: SceneCutPlan | None = None,
) -> BatchImproveStats:
    """
    Универсальный метод для обработки батча (апскейл или денойз)
    :param processing_type: Тип обработки (UPSCALE или DENOISE)
    :param ai_threads: Параметры тредов для ИИ обработки
    :param ai_tool_path: Путь к исполняемому файлу ИИ инструмента
    :param batch_num: Номер батча для обработки
    :param max_retries: Максимальное количество попыток
    """
    config = PROCESSING_CONFIG[processing_type]
    input_dir = Path(config["input_dir"]) / f"batch_{batch_num}"
    output_dir = create_dir(config["output_dir"], f"batch_{batch_num}")
    source_frame_count = count_frames_in_certain_batches(
        input_dir.parent,
        just_one_batch=batch_num,
    )

    if not Path(ai_tool_path).exists():
        logger.error(f"ИИ утилита не найдена: {ai_tool_path}")
        raise FileNotFoundError(ai_tool_path)

    effective_input_dir = input_dir
    duplicate_map: dict[str, str] = {}
    static_temp_input_dir: Path | None = None
    static_expected_frame_count = 0
    if (
        processing_type in {ProcessingType.DENOISE, ProcessingType.UPSCALE}
        and scene_cut_plan is not None
        and scene_cut_plan.static_runs
    ):
        static_temp_input_dir = (
            output_dir.parent
            / f"_static_scene_guard_{processing_type.value}_batch_{batch_num}"
        )
        effective_input_dir, duplicate_map = _prepare_static_stage_input(
            input_dir=input_dir,
            temp_input_dir=static_temp_input_dir,
            batch_num=batch_num,
            static_runs=scene_cut_plan.static_runs,
        )
        if duplicate_map:
            static_expected_frame_count = count_frames_in_certain_batches(
                input_dir.parent,
                just_one_batch=batch_num,
            )
            _clear_top_level_frames(output_dir)
            logger.debug(
                f"Static Scene Guard: {processing_type.value} batch_{batch_num}: "
                f"AI обрабатывает на {len(duplicate_map)} кадров меньше"
            )

    # Формируем команду в зависимости от типа обработки
    command = [ai_tool_path, "-i", str(effective_input_dir), "-o", output_dir]
    # Общие параметры для всех типов обработки
    common_args = ("-f", OUTPUT_IMAGE_FORMAT, "-j", ai_threads)

    # Специфические параметры для каждого типа обработки
    if processing_type == ProcessingType.DENOISE:
        command.extend(
            [
                "-m",
                config["model_dir"],
                "-n",
                str(config["denoise_factor"]),
                "-s",
                str(config["scale_factor"]),
                *common_args,
            ]
        )
    elif processing_type == ProcessingType.UPSCALE:
        command.extend(
            [
                "-n",
                config["model_name"],
                "-s",
                str(config["scale_factor"]),
                "-m",
                config["model_dir"],
                *common_args,
            ]
        )
    elif processing_type == ProcessingType.INTERPOLATE:
        if scene_cut_plan is not None and (
            scene_cut_plan.cuts or scene_cut_plan.static_runs
        ):
            return _improve_interpolation_batch_with_scene_cut_guard(
                ai_threads=ai_threads,
                ai_tool_path=ai_tool_path,
                batch_num=batch_num,
                input_dir=input_dir,
                output_dir=output_dir,
                scene_cut_plan=scene_cut_plan,
                max_retries=max_retries,
            )
        frames_in_batch = count_frames_in_certain_batches(
            directory=UPSCALED_BATCHES_DIR, just_one_batch=batch_num
        )
        command = _build_rife_command(
            ai_tool_path=ai_tool_path,
            ai_threads=ai_threads,
            input_dir=effective_input_dir,
            output_dir=output_dir,
            frame_count=frames_in_batch,
        )

    try:
        _run_ai_command(
            command,
            config=config,
            batch_num=batch_num,
            max_retries=max_retries,
        )
        if duplicate_map:
            _materialize_static_stage_outputs(
                output_dir=output_dir,
                duplicate_map=duplicate_map,
            )
            actual_output_count = len(list(output_dir.glob(f"*.{OUTPUT_IMAGE_FORMAT}")))
            if actual_output_count != static_expected_frame_count:
                raise RuntimeError(
                    f"Static Scene Guard: batch_{batch_num} создал "
                    f"{actual_output_count} кадров, ожидалось "
                    f"{static_expected_frame_count}"
                )
    finally:
        if static_temp_input_dir is not None and not KEEP_TEMP_FILES:
            shutil.rmtree(static_temp_input_dir, ignore_errors=True)
    return BatchImproveStats(
        source_frames=source_frame_count,
        ai_input_frames=source_frame_count - len(duplicate_map),
        static_frames_skipped=len(duplicate_map),
        interpolation_segments=(
            1
            if processing_type == ProcessingType.INTERPOLATE and source_frame_count
            else 0
        ),
        rife_calls=(
            1
            if processing_type == ProcessingType.INTERPOLATE and source_frame_count
            else 0
        ),
    )


async def monitor_progress(
    source_frames: int,
    is_processing: list,
    batch_numbers: range,
    processing_type: ProcessingType,
    progress_callback: Callable[..., None] | None = None,
) -> None:
    """
    Универсальный мониторинг прогресса с умеренным логированием.
    :param source_frames: Количество входных кадров для обработки
    :param is_processing: Флаг активной обработки
    :param batch_numbers: Диапазон номеров батчей
    :param processing_type: Тип обработки для отображения
    """
    processed_frames = 0
    config = PROCESSING_CONFIG[processing_type]
    display_name = config["display_name"]
    output_dir = config["output_dir"]
    target_frames = (
        source_frames * FRAMES_MULTIPLY_FACTOR
        if processing_type == ProcessingType.INTERPOLATE
        else source_frames
    )
    target_frames = max(1, target_frames)

    last_logged = 0.0
    last_logged_percent = -5.0
    log_interval = 10  # логировать каждые n секунд
    poll_interval = 2  # проверять появление новых кадров чаще, чем логировать
    rate = ProgressRateEstimator()
    batch_label = f"{batch_numbers.start}-{batch_numbers.stop - 1}"

    while is_processing[0]:
        try:
            current_frames = min(
                target_frames,
                count_frames_in_certain_batches(output_dir, batch_numbers),
            )

            if current_frames > processed_frames:
                processed_frames = current_frames
                current_time = time.time()
                progress_percent = min(100.0, (processed_frames / target_frames) * 100)
                speed = rate.update(processed_frames, current_time)
                elapsed = current_time - rate.start_time
                eta_text = rate.eta_text(
                    total=target_frames,
                    count=processed_frames,
                    percent=progress_percent,
                    now=current_time,
                )
                snapshot = ProgressSnapshot(
                    processed_frames=processed_frames,
                    total_frames=target_frames,
                    percent=progress_percent,
                    elapsed_text=format_duration(elapsed),
                    eta_text=eta_text,
                    speed_fps=speed,
                )
                _call_progress_callback(
                    progress_callback,
                    min(100.0, progress_percent),
                    snapshot,
                )

                if progress_percent < 100 and (
                    current_time - last_logged >= log_interval
                    or progress_percent - last_logged_percent >= 5
                ):
                    logger.info(
                        f"{display_name}: батчи {batch_label} | "
                        f"{progress_percent:.1f}% | "
                        f"{processed_frames}/{target_frames} кадров | "
                        f"прошло {format_duration(elapsed)} | "
                        f"осталось {eta_text} | {speed:.1f} FPS"
                    )
                    last_logged = current_time
                    last_logged_percent = progress_percent
            if processed_frames >= target_frames:
                break
            await asyncio.sleep(poll_interval)
        except Exception as error:
            logger.error(f"Ошибка мониторинга прогресса: {str(error)}")
            await asyncio.sleep(1)

    final_count = min(
        target_frames,
        max(
            processed_frames, count_frames_in_certain_batches(output_dir, batch_numbers)
        ),
    )
    total_time = time.time() - rate.start_time
    average_speed = final_count / max(total_time, 0.001)
    snapshot = ProgressSnapshot(
        processed_frames=target_frames,
        total_frames=target_frames,
        percent=100.0,
        elapsed_text=format_duration(total_time),
        eta_text="00:00",
        speed_fps=average_speed,
    )
    _call_progress_callback(progress_callback, 100.0, snapshot)
    logger.success(
        f"{display_name}: батчи {batch_label} завершены за "
        f"{format_duration(total_time)}, средняя скорость {average_speed:.1f} FPS"
    )


def _select_frame_guard_scan(
    scan_result: SceneCutScanResult,
    batch_numbers: range,
) -> SceneCutScanResult:
    selected_numbers = tuple(batch_numbers)
    missing = [
        batch_num
        for batch_num in selected_numbers
        if batch_num not in scan_result.plans_by_batch
    ]
    if missing:
        raise ValueError(
            "Frame Guard plan не содержит батчи: "
            + ", ".join(str(batch_num) for batch_num in missing)
        )
    plans = {
        batch_num: scan_result.plans_by_batch[batch_num]
        for batch_num in selected_numbers
    }
    cuts = {
        (cut.from_frame, cut.to_frame): cut
        for plan in plans.values()
        for cut in plan.cuts
    }
    static_runs = {
        (run.start_frame, run.end_frame): run
        for plan in plans.values()
        for run in plan.static_runs
    }
    return SceneCutScanResult(
        plans_by_batch=plans,
        cuts=tuple(cuts[key] for key in sorted(cuts)),
        static_runs=tuple(static_runs[key] for key in sorted(static_runs)),
        requested_method=scan_result.requested_method,
        method=scan_result.method,
    )


def _log_static_guard_stage_summary(
    *,
    processing_type: ProcessingType,
    source_frames: int,
    static_runs: tuple[StaticSceneRun, ...],
    batch_stats: list[BatchImproveStats],
) -> None:
    static_frames = sum(run.frame_count for run in static_runs)
    static_percent = static_frames * 100 / max(1, source_frames)
    skipped_frames = sum(stats.static_frames_skipped for stats in batch_stats)
    ai_input_frames = sum(stats.ai_input_frames for stats in batch_stats)
    details = (
        f"static runs={len(static_runs)}, "
        f"static frames={static_frames}/{source_frames} ({static_percent:.1f}%), "
        f"AI input={ai_input_frames}, skipped={skipped_frames}"
    )
    if processing_type == ProcessingType.INTERPOLATE:
        details += (
            f", segments={sum(stats.interpolation_segments for stats in batch_stats)}, "
            f"RIFE calls={sum(stats.rife_calls for stats in batch_stats)}, "
            "unprofitable bypasses="
            f"{sum(stats.optimization_bypassed for stats in batch_stats)}"
        )
    logger.info(f"Static Scene Guard [{processing_type.value}]: {details}")


async def improve_batches(
    processing_type: ProcessingType,
    process_threads: int,
    ai_threads: str,
    ai_tool_path: str,
    start_batch: int,
    end_batch: int,
    max_retries: int = MAX_RETRIES,
    progress_callback: Callable[..., None] | None = None,
    frame_guard_scan: SceneCutScanResult | None = None,
    source_fps: float | None = None,
) -> None:
    """
    Универсальная функция для асинхронной обработки диапазона батчей
    :param processing_type: Тип обработки (UPSCALE или DENOISE)
    :param process_threads: Количество процессов для параллельной обработки
    :param ai_threads: Параметры тредов для ИИ обработки
    :param ai_tool_path: Путь к исполняемому файлу ИИ инструмента
    :param start_batch: Начальный номер батча
    :param end_batch: Конечный номер батча
    :param max_retries: Максимальное количество попыток
    """
    config = PROCESSING_CONFIG[processing_type]
    batches_range = range(start_batch, end_batch + 1)
    source_frames = count_frames_in_certain_batches(config["input_dir"], batches_range)
    is_processing = [True]
    frame_guard_plans: dict[int, SceneCutPlan] = {}

    if start_batch == end_batch:
        process_threads = 1

    scan_result: SceneCutScanResult | None = None
    should_scan = STATIC_SCENE_GUARD_ENABLED or (
        processing_type == ProcessingType.INTERPOLATE and SCENE_CUT_GUARD_ENABLED
    )
    if should_scan:
        if frame_guard_scan is None:
            analysis_started = time.perf_counter()
            scan_result = build_scene_cut_plans(
                input_root=config["input_dir"],
                batch_numbers=batches_range,
                image_format=OUTPUT_IMAGE_FORMAT,
                method=SCENE_CUT_DETECTION_METHOD,
                threshold=SCENE_CUT_THRESHOLD,
                min_scene_frames=SCENE_CUT_MIN_SCENE_FRAMES,
                static_min_run_frames=calculate_static_scene_min_run_frames(
                    source_fps,
                    STATIC_SCENE_MIN_DURATION_SECONDS,
                ),
            )
            logger.info(
                "Frame Guard analysis: "
                f"кадров={source_frames}, cuts={len(scan_result.cuts)}, "
                f"static runs={len(scan_result.static_runs)}, "
                f"время={time.perf_counter() - analysis_started:.3f} с"
            )
        else:
            scan_result = _select_frame_guard_scan(frame_guard_scan, batches_range)
        for batch_num, plan in scan_result.plans_by_batch.items():
            frame_guard_plans[batch_num] = SceneCutPlan(
                cuts=(
                    plan.cuts
                    if processing_type == ProcessingType.INTERPOLATE
                    and SCENE_CUT_GUARD_ENABLED
                    else ()
                ),
                static_runs=(plan.static_runs if STATIC_SCENE_GUARD_ENABLED else ()),
            )

    if processing_type == ProcessingType.INTERPOLATE:
        if SCENE_CUT_GUARD_ENABLED and scan_result is not None:
            method_note = (
                f" (requested: {scan_result.requested_method})"
                if scan_result.requested_method != scan_result.method
                else ""
            )
            logger.info(
                "Scene Cut Guard включен: "
                f"method={scan_result.method}{method_note}, "
                f"threshold={SCENE_CUT_THRESHOLD}, "
                f"min_scene_frames={SCENE_CUT_MIN_SCENE_FRAMES}, "
                f"батчи {start_batch}-{end_batch}, "
                f"найдено cuts={len(scan_result.cuts)}"
            )
            if SCENE_CUT_DEBUG:
                report_path = write_scene_cut_debug(
                    report_path=Path(TMP_VIDEO_PATH) / "scene_cuts.json",
                    enabled=True,
                    requested_method=scan_result.requested_method,
                    method=scan_result.method,
                    threshold=SCENE_CUT_THRESHOLD,
                    min_scene_frames=SCENE_CUT_MIN_SCENE_FRAMES,
                    cuts=scan_result.cuts,
                    static_runs=(
                        scan_result.static_runs if STATIC_SCENE_GUARD_ENABLED else ()
                    ),
                )
                logger.info(f"Scene Cut Guard debug сохранен: {report_path}")
        else:
            logger.info("Scene Cut Guard отключен")
        output_frames = source_frames * FRAMES_MULTIPLY_FACTOR
        logger.info(
            f"Начало {config['start_name']} батчей {start_batch}-{end_batch}: "
            f"исходных кадров {source_frames}, "
            f"ожидаемых кадров на выходе {output_frames}, "
            f"процессов {process_threads}"
        )
    else:
        logger.info(
            f"Начало {config['start_name']} батчей {start_batch}-{end_batch}: "
            f"кадров {source_frames}, процессов {process_threads}"
        )

    monitor_task = asyncio.create_task(
        monitor_progress(
            source_frames,
            is_processing,
            batches_range,
            processing_type,
            progress_callback,
        )
    )

    try:
        loop = asyncio.get_event_loop()
        with ProcessPoolExecutor(max_workers=process_threads) as executor:
            tasks = [
                loop.run_in_executor(
                    executor,
                    _improve_batch,
                    processing_type,
                    ai_threads,
                    ai_tool_path,
                    batch_num,
                    max_retries,
                    frame_guard_plans.get(batch_num),
                )
                for batch_num in batches_range
            ]
            batch_stats = await asyncio.gather(*tasks)
    except Exception as error:
        logger.error(f"Ошибка при {config['error_name']} батчей: {str(error)}")
        raise
    finally:
        is_processing[0] = False  # завершаем мониторинг прогресса
        await monitor_task  # ожидаем завершения задачи мониторинга

    if STATIC_SCENE_GUARD_ENABLED and scan_result is not None:
        _log_static_guard_stage_summary(
            processing_type=processing_type,
            source_frames=source_frames,
            static_runs=scan_result.static_runs,
            batch_stats=batch_stats,
        )
