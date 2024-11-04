import asyncio
import glob
import os
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from pathlib import Path

from colorama import Fore, Style
from tqdm import tqdm

from src.config.settings import (
    ALLOWED_THREADS,
    INPUT_BATCHES_DIR,
    OUTPUT_BATCHES_DIR,
    OUTPUT_IMAGE_FORMAT,
    START_BATCH_TO_UPSCALE,
    UPSCALE_FACTOR,
    UPSCALE_MODEL_NAME,
)
from src.utils.file_utils import create_dir, delete_dir, delete_object


def delete_upscaled_frames(del_only_dirs=True):
    """
    Удаляет кадры из указанной директории.
    Если `del_only_dirs` установлено в True, удаляются только директории, иначе — и файлы, и директории.
    :param del_only_dirs: Флаг для удаления только директорий. Если False, удаляет и файлы, и директории.
    """
    file_paths = glob.glob(os.path.join(OUTPUT_BATCHES_DIR, "*"))

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


def process_frame(frame_path: str, output_path: str):
    """Функция для обработки одного фрейма."""
    model_dir = "/home/uzver_pro/PythonProjects/anime_enhancement/src/utils/realesrgan/models"
    model_name = "realesr-animevideov3-x2"
    command = [
        "/home/uzver_pro/PythonProjects/anime_enhancement/src/utils/realesrgan/realesrgan-linux/realesrgan-ncnn-vulkan",
        "-i", frame_path,
        "-o", output_path,
        "-n", model_name,
        "-s", "2",
        "-f", "jpg",
        "-m", model_dir,
    ]

    process = subprocess.run(command)
    return process.returncode


async def upscale_batch(batch_num: int):
    """Асинхронная функция для обработки всех фреймов в батче."""
    input_dir = Path(INPUT_BATCHES_DIR) / f"batch_{batch_num}"
    output_dir = create_dir(OUTPUT_BATCHES_DIR, f"batch_{batch_num}")

    frame_paths = list(Path(input_dir).glob(f"*.{OUTPUT_IMAGE_FORMAT}"))
    total_frames = len(frame_paths)

    # Инициализация прогресс-бара
    with tqdm(
        total=total_frames,
        desc=f"{Fore.GREEN}Обработка батча {batch_num}{Style.RESET_ALL}",
        unit="фрейм",
        colour="green",
        unit_scale=True,
    ) as pbar:
        with ThreadPoolExecutor(max_workers=ALLOWED_THREADS) as executor:
            loop = asyncio.get_event_loop()
            tasks = [
                loop.run_in_executor(
                    executor,
                    process_frame,
                    str(frame_path),
                    f"{output_dir}/{frame_path.name}",
                )
                for frame_path in frame_paths
            ]
            for future in asyncio.as_completed(tasks):
                return_code = await future
                if return_code != 0:
                    print(f"Ошибка при обработке фрейма")
                pbar.update(1)  # Обновляем прогресс-бар после обработки каждого фрейма


async def upscale_batches(
    start_batch: int = START_BATCH_TO_UPSCALE, end_batch: int = 13
):
    """Асинхронная функция для обработки всех батчей."""
    tasks = [
        upscale_batch(batch_num) for batch_num in range(start_batch, end_batch + 1)
    ]
    await asyncio.gather(*tasks)


# def _upscale(batch_num: int):
#     """Функция улучшения фреймов в батче."""
#     input_dir = Path(INPUT_BATCHES_DIR) / f"batch_{batch_num}"
#     output_dir = create_dir(OUTPUT_BATCHES_DIR, f"batch_{batch_num}")
#
#     command = [
#         "./src/utils/realesrgan/realesrgan-ncnn-vulkan",
#         "-i", str(input_dir),
#         "-o", output_dir,
#         "-n", UPSCALE_MODEL_NAME,
#         "-s", str(UPSCALE_FACTOR),
#         "-f", OUTPUT_IMAGE_FORMAT,
#     ]
#
#     result = subprocess.run(command, capture_output=True, text=True)
#     if result.returncode != 0:
#         print(f"Ошибка в батче {batch_num}: {result.stderr}")
#     else:
#         print(f"Батч {batch_num} успешно обработан.")
#
#
# def upscale_batches(start_batch: int = START_BATCH_TO_UPSCALE, end_batch: int = 13):
#     batch_numbers = range(start_batch, end_batch + 1)
#
#     # Параллельная обработка батчей
#     with ProcessPoolExecutor(max_workers=ALLOWED_THREADS) as executor:
#         future_to_batch = {executor.submit(_upscale, batch_num): batch_num for batch_num in batch_numbers}
#
#         for future in as_completed(future_to_batch):
#             batch_num = future_to_batch[future]
#             try:
#                 future.result()
#             except Exception as exc:
#                 print(f"Батч {batch_num} вызвал исключение: {exc}")
