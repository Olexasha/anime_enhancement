import asyncio
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor
from enum import Enum
from pathlib import Path
from typing import Any, Dict

from src.config.settings import (
    DENOISE_FACTOR,
    DENOISED_BATCHES_DIR,
    INPUT_BATCHES_DIR,
    OUTPUT_IMAGE_FORMAT,
    REALESRGAN_MODEL_DIR,
    REALESRGAN_MODEL_NAME,
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


# Конфигурация для каждого типа обработки
PROCESSING_CONFIG: Dict[ProcessingType, Dict[str, Any]] = {
    ProcessingType.UPSCALE: {
        "input_dir": DENOISED_BATCHES_DIR,
        "output_dir": UPSCALED_BATCHES_DIR,
        "model_dir": REALESRGAN_MODEL_DIR,
        "model_name": REALESRGAN_MODEL_NAME,
        "scale_factor": UPSCALE_FACTOR,
        "display_name": "Upscale",
    },
    ProcessingType.DENOISE: {
        "input_dir": INPUT_BATCHES_DIR,
        "output_dir": DENOISED_BATCHES_DIR,
        "model_dir": WAIFU2X_MODEL_DIR,
        "scale_factor": WAIFU2X_UPSCALE_FACTOR,
        "denoise_factor": DENOISE_FACTOR,
        "display_name": "Denoise",
    },
}


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

    if processing_type == ProcessingType.UPSCALE:
        command.extend(
            [
                "-n",
                config["model_name"],
                "-s",
                str(config["scale_factor"]),
                "-f",
                OUTPUT_IMAGE_FORMAT,
                "-m",
                config["model_dir"],
                "-j",
                ai_threads,
            ]
        )
    elif processing_type == ProcessingType.DENOISE:
        command.extend(
            [
                "-m",
                config["model_dir"],
                "-n",
                str(config["denoise_factor"]),
                "-s",
                str(config["scale_factor"]),
                "-f",
                OUTPUT_IMAGE_FORMAT,
                "-j",
                ai_threads,
            ]
        )

    for attempt in range(max_retries):
        try:
            logger.debug(
                f"Запуск {config['display_name'].lower()}а батча {batch_num} с параметрами: {ai_threads}. "
                f"Попытка: {attempt + 1}/{max_retries}"
            )
            result = subprocess.run(command, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"Ошибка в батче {batch_num}: {result.stderr}")
                raise RuntimeError(
                    f"Ошибка {config['display_name'].lower()}а батча {batch_num}"
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
                    f"Не удалось {config['display_name'].lower()}ить {batch_num} после {max_retries} попыток"
                )

        except Exception as error:
            logger.error(f"Неожиданная ошибка в батче {batch_num}: {str(error)}")
            raise


async def monitor_progress(
    total_frames: int,
    is_processing: list,
    batch_numbers: range,
    processing_type: ProcessingType,
) -> None:
    """
    Универсальный мониторинг прогресса с частым обновлением и визуализацией
    :param total_frames: Общее количество фреймов для обработки
    :param is_processing: Флаг активной обработки
    :param batch_numbers: Диапазон номеров батчей
    :param processing_type: Тип обработки для отображения
    """
    processed_frames = 0
    start_time = time.time()
    config = PROCESSING_CONFIG[processing_type]
    display_name = config["display_name"]
    output_dir = config["output_dir"]

    last_logged = 0
    log_interval = 10  # логировать каждые n секунд

    while is_processing[0]:
        try:
            current_frames = count_frames_in_certain_batches(output_dir, batch_numbers)

            if current_frames > processed_frames:
                processed_frames = current_frames
                progress_percent = (processed_frames / total_frames) * 100

                current_time = time.time()
                if (
                    current_time - last_logged >= log_interval
                    or progress_percent >= 100
                    or processed_frames == total_frames
                ):
                    elapsed = current_time - start_time
                    fps = processed_frames / elapsed if elapsed > 0 else 0
                    remaining = (
                        (total_frames - processed_frames) / fps if fps > 0 else 0
                    )

                    logger.info(
                        f"{display_name} фреймов ({batch_numbers.start}-{batch_numbers.stop - 1}): "
                        f"{processed_frames}/{total_frames} ({progress_percent:.1f}%) | "
                        f"Прошло: {elapsed:.1f}сек | Осталось: {remaining:.1f}сек"
                    )
                    last_logged = current_time
            if processed_frames >= total_frames:
                break
            await asyncio.sleep(log_interval)
        except Exception as error:
            logger.error(f"Error monitoring progress: {str(error)}")
            await asyncio.sleep(1)

    total_time = time.time() - start_time
    logger.info(
        f"{display_name} фреймов: {total_frames}/{total_frames} "
        f"(100%) | Прошло: {total_time:.1f}сек"
    )
    logger.success(
        f"Обработка завершена. (Средняя скорость: {total_frames / total_time:.1f} FPS)"
    )


async def improve_batches(
    processing_type: ProcessingType,
    process_threads: int,
    ai_threads: str,
    ai_tool_path: str,
    start_batch: int,
    end_batch: int,
    max_retries: int = MAX_RETRIES,
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
    total_frames = count_frames_in_certain_batches(config["input_dir"], batches_range)
    is_processing = [True]

    logger.info(
        f"Начало {config['display_name'].lower()}`а батчей {start_batch}-{end_batch} "
        f"(всего фреймов: {total_frames}, процессов: {process_threads})"
    )

    monitor_task = asyncio.create_task(
        monitor_progress(total_frames, is_processing, batches_range, processing_type)
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
        logger.error(
            f"Ошибка при {config['display_name'].lower()}е батчей: {str(error)}"
        )
        raise
    finally:
        is_processing[0] = False  # завершаем мониторинг прогресса
        await monitor_task  # ожидаем завершения задачи мониторинга
