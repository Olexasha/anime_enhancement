import asyncio
import glob
import os
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from colorama import Fore, Style
from tqdm import tqdm

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


def delete_frames(del_upscaled: bool, del_only_dirs: bool = True):
    """
    Удаляет кадры из указанной директории.
    Если `del_only_dirs` установлено в True, удаляются только директории, иначе — и файлы, и директории.
    :param del_upscaled: Флаг для удаления апскейленных фреймов. Если True, удаляет фреймы из OUTPUT_BATCHES_DIR.
    :param del_only_dirs: Флаг для удаления только директорий. Если False, удаляет и файлы, и директории.
    """
    if del_upscaled:
        file_paths = glob.glob(os.path.join(OUTPUT_BATCHES_DIR, "*"))
    else:
        file_paths = glob.glob(os.path.join(INPUT_BATCHES_DIR, "*"))

    for file_path in file_paths:
        try:
            # Проверка типа объекта перед удалением
            if del_only_dirs and os.path.isdir(file_path):
                delete_dir(file_path)
            elif not del_only_dirs:
                delete_object(file_path)
            else:
                print(f"Пропущен файл: {file_path} (del_only_dirs=True)")
        except Exception as e:
            print(f"Не удалось удалить {file_path}. Причина: {e}")


async def monitor_progress(
    total_frames: int, is_processing: list, batch_numbers: range
):
    """Мониторинг прогресса с одним глобальным прогресс-баром."""
    processed_frames = 0
    with tqdm(
        total=total_frames,
        desc=f"{Fore.GREEN}Обработка батчей "
        f"{batch_numbers[0]}-{batch_numbers[-1]}{Style.RESET_ALL}",
        unit=f"фрейм{Style.RESET_ALL}",
        ncols=150,
        colour="green",
        file=sys.stdout,
    ) as pbar:
        while is_processing[0]:
            if processed_frames >= total_frames:
                break
            processed_frames = count_frames_in_certain_batches(
                OUTPUT_BATCHES_DIR, batch_numbers
            )
            pbar.n = processed_frames
            pbar.refresh()
            await asyncio.sleep(5)  # Пауза для периодического обновления
        pbar.n = processed_frames
        pbar.refresh()
        pbar.close()


def _upscale(ai_threads: str, ai_realesrgan_path: str, batch_num: int):
    """Функция улучшения фреймов в батче."""
    input_dir = Path(INPUT_BATCHES_DIR) / f"batch_{batch_num}"
    output_dir = create_dir(OUTPUT_BATCHES_DIR, f"batch_{batch_num}")

    if not os.path.exists(ai_realesrgan_path):
        print(
            f"Файл скрипта нейронки для батча {batch_num} не найден: {ai_realesrgan_path}"
        )
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

    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Ошибка в батче {batch_num}: {result.stderr}")


async def upscale_batches(
    process_threads: int,
    ai_threads: str,
    ai_realesrgan_path: str,
    start_batch: int,
    end_batch: int,
):
    # Считаем общее количество фреймов для отслеживания прогресса
    batches_range = range(start_batch, end_batch + 1)
    frames_in_curr_batches = count_frames_in_certain_batches(
        INPUT_BATCHES_DIR, batches_range
    )
    is_processing = [True]

    # Запускаем задачу мониторинга прогресса
    monitor_task = asyncio.create_task(
        monitor_progress(frames_in_curr_batches, is_processing, batches_range)
    )

    try:
        # Запускаем обработку батчей с использованием ProcessPoolExecutor
        loop = asyncio.get_event_loop()
        with ProcessPoolExecutor(max_workers=process_threads) as executor:
            tasks = [
                loop.run_in_executor(
                    executor, _upscale, ai_threads, ai_realesrgan_path, batch_num
                )
                for batch_num in batches_range
            ]
            # Ожидаем завершения всех задач апскейлинга
            await asyncio.gather(*tasks)

    finally:
        is_processing[0] = False  # Завершаем мониторинг прогресса
        await monitor_task  # Ожидаем завершения задачи мониторинга
        print(f"Батчи {start_batch}-{end_batch} обработаны.\n")
