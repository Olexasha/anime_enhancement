import asyncio
import inspect
import subprocess
import time
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

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
    OUTPUT_IMAGE_FORMAT,
    REALESRGAN_MODEL_DIR,
    REALESRGAN_MODEL_NAME,
    RIFE_MODEL_DIR,
    TIME_STEP,
    UPSCALE_FACTOR,
    UPSCALED_BATCHES_DIR,
    WAIFU2X_MODEL_DIR,
    WAIFU2X_UPSCALE_FACTOR,
)
from src.files.file_actions import create_dir
from src.frames.frames_helpers import count_frames_in_certain_batches
from src.utils.logger import logger

MAX_RETRIES = 3  # макс количество попыток при неудаче на обработке фреймов
RETRY_DELAY = 2  # задержка между попытками в сек


class ProcessingType(Enum):
    """Типы обработки фреймов"""

    UPSCALE = "upscale"
    DENOISE = "denoise"
    INTERPOLATE = "interpolate"


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


def _improve_batch(
    processing_type: ProcessingType,
    ai_threads: str,
    ai_tool_path: str,
    batch_num: int,
    max_retries: int = MAX_RETRIES,
) -> None:
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

    if not Path(ai_tool_path).exists():
        logger.error(f"ИИ утилита не найдена: {ai_tool_path}")
        raise FileNotFoundError(ai_tool_path)

    # Формируем команду в зависимости от типа обработки
    command = [ai_tool_path, "-i", str(input_dir), "-o", output_dir]
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
        command.extend(
            [
                "-m",
                config["model_dir"],
                *common_args,
            ]
        )
        if FRAMES_MULTIPLY_FACTOR > 2:
            frames_in_batch = count_frames_in_certain_batches(
                directory=UPSCALED_BATCHES_DIR, just_one_batch=batch_num
            )
            command.extend(
                (
                    "-n",
                    str(config["num_frame"] * frames_in_batch),
                    "-s",
                    str(config["time_step"]),
                )
            )

        # Добавляем флаги только для интерполяции
        flags = []
        if ENABLE_UHD_MODE:
            flags.append("-u")
        if ENABLE_SPATIAL_TTA_MODE:
            flags.append("-x")
        if ENABLE_TEMPORAL_TTA_MODE:
            flags.append("-z")

        command.extend(flags)

    cmd_args = [str(arg) for arg in command]
    logger.debug(" ".join(cmd_args))

    for attempt in range(max_retries):
        try:
            logger.debug(
                f"Запуск {config['display_name'].lower()} батча {batch_num} с параметрами: {ai_threads}. "
                f"Попытка: {attempt + 1}/{max_retries}"
            )
            result = subprocess.run(command, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"Ошибка в батче {batch_num}: {result.stderr}")
                raise RuntimeError(
                    f"Ошибка этапа {config['display_name']} в батче {batch_num}"
                )
            return

        except subprocess.CalledProcessError as error:
            logger.error(
                f"Ошибка в батче {batch_num} (попытка {attempt + 1}): {error.stderr}"
            )
            if attempt < max_retries - 1:
                time.sleep(RETRY_DELAY)
            else:
                raise RuntimeError(
                    f"Не удалось обработать батч {batch_num} "
                    f"на этапе {config['display_name']} после {max_retries} попыток"
                ) from error

        except Exception as error:
            logger.error(f"Неожиданная ошибка в батче {batch_num}: {str(error)}")
            raise


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


async def improve_batches(
    processing_type: ProcessingType,
    process_threads: int,
    ai_threads: str,
    ai_tool_path: str,
    start_batch: int,
    end_batch: int,
    max_retries: int = MAX_RETRIES,
    progress_callback: Callable[..., None] | None = None,
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

    if start_batch == end_batch:
        process_threads = 1

    if processing_type == ProcessingType.INTERPOLATE:
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
                )
                for batch_num in batches_range
            ]
            await asyncio.gather(*tasks)
    except Exception as error:
        logger.error(f"Ошибка при {config['error_name']} батчей: {str(error)}")
        raise
    finally:
        is_processing[0] = False  # завершаем мониторинг прогресса
        await monitor_task  # ожидаем завершения задачи мониторинга
