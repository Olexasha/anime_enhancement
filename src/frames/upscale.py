import asyncio
import glob
import os
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from src.config.settings import (
    INPUT_BATCHES_DIR,
    MODEL_DIR,
    MODEL_NAME,
    OUTPUT_BATCHES_DIR,
    OUTPUT_IMAGE_FORMAT,
    UPSCALE_FACTOR,
)
from src.files.file_actions import create_dir, delete_dir, delete_object
from src.frames.frames_helpers import count_frames_in_certain_batches
from src.utils.logger import logger


def delete_frames(del_upscaled: bool, del_only_dirs: bool = True):
    """
    Удаляет кадры из указанной директории.
    Если `del_only_dirs` установлено в True, удаляются только директории, иначе — и файлы, и директории.
    :param del_upscaled: Флаг для удаления апскейленных фреймов. Если True, удаляет фреймы из OUTPUT_BATCHES_DIR.
    :param del_only_dirs: Флаг для удаления только директорий. Если False, удаляет и файлы, и директории.
    """
    target_dir = OUTPUT_BATCHES_DIR if del_upscaled else INPUT_BATCHES_DIR
    file_paths = glob.glob(os.path.join(target_dir, "*"))
    logger.debug(
        f"Начало удаления кадров из {target_dir} (del_only_dirs={del_only_dirs})"
    )

    for file_path in file_paths:
        try:
            if del_only_dirs and os.path.isdir(file_path):
                delete_dir(file_path)
            elif not del_only_dirs:
                delete_object(file_path)
            else:
                logger.debug(f"Пропущен файл: {file_path} (del_only_dirs=True)")
        except Exception as error:
            logger.error(f"Не удалось удалить {file_path}: {str(error)}")


async def monitor_progress(
    total_frames: int, is_processing: list, batch_numbers: range
) -> None:
    """Мониторинг прогресса с частым обновлением и визуализацией"""
    processed_frames = 0
    start_time = time.time()

    last_logged = 0
    log_every_sec = 15  # логировать каждые N секунд

    while is_processing[0]:
        current_frames = count_frames_in_certain_batches(
            OUTPUT_BATCHES_DIR, batch_numbers
        )

        # Обновляем только если количество изменилось
        if current_frames > processed_frames:
            processed_frames = current_frames
            progress_percent = (processed_frames / total_frames) * 100

            # Логируем регулярно или при значительном прогрессе
            current_time = time.time()
            if (
                current_time - last_logged >= log_every_sec
                or progress_percent >= 100
                or processed_frames == total_frames
            ):
                elapsed = current_time - start_time
                fps = processed_frames / elapsed if elapsed > 0 else 0
                remaining = (total_frames - processed_frames) / fps if fps > 0 else 0

                logger.info(
                    f"Апскейл фреймов: {processed_frames}/{total_frames} "
                    f"({progress_percent:.1f}%) | "
                    f"Прошло: {elapsed:.1f}сек | "
                    f"Осталось: {remaining:.1f}сек"
                )
                last_logged = current_time
        if processed_frames >= total_frames:
            break
        await asyncio.sleep(5)  # Проверяем прогресс каждые 5 секунд
    total_time = time.time() - start_time
    logger.info(
        f"Апскейл фреймов: {total_frames}/{total_frames} "
        f"(100%) | Прошло: {total_time:.1f}сек"
    )
    logger.success(
        f"Обработка завершена. (Средняя скорость: {total_frames / total_time:.1f} FPS)"
    )


def _upscale(ai_threads: str, ai_realesrgan_path: str, batch_num: int):
    """Выполняет апскейл фреймов в указанном батче."""
    input_dir = Path(INPUT_BATCHES_DIR) / f"batch_{batch_num}"
    output_dir = create_dir(OUTPUT_BATCHES_DIR, f"batch_{batch_num}")

    if not os.path.exists(ai_realesrgan_path):
        logger.error(f"Файл скрипта не найден: {ai_realesrgan_path}")
        raise FileNotFoundError(ai_realesrgan_path)

    command = [
        ai_realesrgan_path,
        "-i", str(input_dir),
        "-o", output_dir,
        "-n", MODEL_NAME,
        "-s", str(UPSCALE_FACTOR),
        "-f", OUTPUT_IMAGE_FORMAT,
        "-m", MODEL_DIR,
        "-j", ai_threads,
    ]

    logger.debug(f"Запуск апскейла батча {batch_num} с параметрами: {ai_threads}")
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"Ошибка в батче {batch_num}: {result.stderr}")
        raise RuntimeError(f"Ошибка апскейла батча {batch_num}")
    logger.debug(f"Успешно обработан батч {batch_num}")


async def upscale_batches(
    process_threads: int,
    ai_threads: str,
    ai_realesrgan_path: str,
    start_batch: int,
    end_batch: int,
):
    """Асинхронно обрабатывает диапазон батчей."""
    batches_range = range(start_batch, end_batch + 1)
    total_frames = count_frames_in_certain_batches(INPUT_BATCHES_DIR, batches_range)
    is_processing = [True]

    logger.info(
        f"Начало обработки батчей {start_batch}-{end_batch} "
        f"(всего фреймов: {total_frames}, процессов: {process_threads})"
    )

    monitor_task = asyncio.create_task(
        monitor_progress(total_frames, is_processing, batches_range)
    )

    try:
        loop = asyncio.get_event_loop()
        with ProcessPoolExecutor(max_workers=process_threads) as executor:
            tasks = [
                loop.run_in_executor(
                    executor, _upscale, ai_threads, ai_realesrgan_path, batch_num
                )
                for batch_num in batches_range
            ]
            await asyncio.gather(*tasks)
    except Exception as error:
        logger.error(f"Ошибка при обработке батчей: {str(error)}")
        raise
    finally:
        is_processing[0] = False  # Завершаем мониторинг прогресса
        await monitor_task  # Ожидаем завершения задачи мониторинга
