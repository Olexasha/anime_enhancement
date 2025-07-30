import asyncio
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import List

from src.config.settings import (
    FRAMES_PER_BATCH,
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

MAX_RETRIES = 3    # макс количество попыток при неудаче на обработке фреймов
RETRY_DELAY = 2    # задержка между попытками в сек


async def delete_frames(del_upscaled: bool, del_only_dirs: bool = True):
    """
    Удаляет кадры из указанной директории.
    Если `del_only_dirs` установлено в True, удаляются только директории, иначе — и файлы, и директории.
    :param del_upscaled: Флаг для удаления апскейленных фреймов. Если True, удаляет фреймы из OUTPUT_BATCHES_DIR.
    :param del_only_dirs: Флаг для удаления только директорий. Если False, удаляет и файлы, и директории.
    """
    target_dir = OUTPUT_BATCHES_DIR if del_upscaled else INPUT_BATCHES_DIR
    logger.debug(
        f"Начало удаления кадров из {target_dir} (del_only_dirs={del_only_dirs})"
    )

    try:
        target_path = Path(target_dir)
        if not target_path.exists():
            logger.warning(f"Директория с фреймами для удаления не существует: {target_dir}")
            return

        items = list(target_path.iterdir())
        
        # удаляем фреймы кусочками (chunks)
        for chunk in _chunk_items(items, FRAMES_PER_BATCH):
            for item in chunk:
                if del_only_dirs and item.is_dir():
                    await delete_dir(str(item))
                elif not del_only_dirs:
                    await delete_object(str(item))
                
    except Exception as error:
        logger.error(f"Ошибка в процессе удаления: {str(error)}")
        raise


def _chunk_items(items: List[Path], chunk_size: int) -> List[List[Path]]:
    """Делит фреймы на кусочки (chunk) для более быстрого удаления"""
    return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]


async def monitor_progress(
    total_frames: int, is_processing: list, batch_numbers: range
) -> None:
    """Мониторинг прогресса с частым обновлением и визуализацией"""
    processed_frames = 0
    start_time = time.time()

    last_logged = 0
    log_interval = 10  # логировать каждые n секунд

    while is_processing[0]:
        try:
            current_frames = count_frames_in_certain_batches(
                OUTPUT_BATCHES_DIR, batch_numbers
            )

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
                    remaining = (total_frames - processed_frames) / fps if fps > 0 else 0

                    logger.info(
                        f"Апскейл фреймов ({batch_numbers.start}-{batch_numbers.stop - 1}): "
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
        f"Апскейл фреймов: {total_frames}/{total_frames} "
        f"(100%) | Прошло: {total_time:.1f}сек"
    )
    logger.success(
        f"Обработка завершена. (Средняя скорость: {total_frames / total_time:.1f} FPS)"
    )


def _upscale(
    ai_threads: str, ai_realesrgan_path: str, batch_num: int, max_retries: int = MAX_RETRIES
) -> None:
    """
    Выполняет апскейл фреймов в указанном батче
    :param ai_threads: Параметры тредов для ИИ апскейл обработки.
    :param ai_realesrgan_path: Путь к исполняемому файлу апскейлера.
    :param batch_num: Количество батчей с дефолт фреймами апскейльнуть.
    :param max_retries: Макс. количество попыток апскейла.
    """
    input_dir = Path(INPUT_BATCHES_DIR) / f"batch_{batch_num}"
    output_dir = create_dir(OUTPUT_BATCHES_DIR, f"batch_{batch_num}")

    if not Path(ai_realesrgan_path).exists():
        logger.error(f"Апскейл утилита не найдена: {ai_realesrgan_path}")
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

    for attempt in range(max_retries):
        try:
            logger.debug(f"Запуск апскейла батча {batch_num} с параметрами: {ai_threads}. "
                         f"Попытка: {attempt + 1}/{max_retries}")
            result = subprocess.run(command, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"Ошибка в батче {batch_num}: {result.stderr}")
                raise RuntimeError(f"Ошибка апскейла батча {batch_num}")
            return

        except subprocess.CalledProcessError as error:
            logger.error(
                f"Ошибка в батче {batch_num} (попытка {attempt + 1}): {error.stderr}"
            )
            if attempt < max_retries - 1:
                time.sleep(RETRY_DELAY)
            else:
                raise RuntimeError(f"Не удалось заапскейлить {batch_num} после {max_retries} попыток")

        except Exception as error:
            logger.error(f"Неожиданная ошибка в батче {batch_num}: {str(error)}")
            raise


async def upscale_batches(
    process_threads: int,
    ai_threads: str,
    ai_realesrgan_path: str,
    start_batch: int,
    end_batch: int,
    max_retries: int = MAX_RETRIES,
) -> None:
    """Асинхронно обрабатывает диапазон батчей"""
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
                    executor, _upscale, ai_threads, ai_realesrgan_path, batch_num, max_retries
                )
                for batch_num in batches_range
            ]
            await asyncio.gather(*tasks)
    except Exception as error:
        logger.error(f"Ошибка при обработке батчей: {str(error)}")
        raise
    finally:
        is_processing[0] = False  # завершаем мониторинг прогресса
        await monitor_task  # ожидаем завершения задачи мониторинга
