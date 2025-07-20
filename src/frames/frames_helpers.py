import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import cv2
from colorama import Fore, Style
from tqdm import tqdm

from src.config.settings import (
    FRAMES_PER_BATCH,
    INPUT_BATCHES_DIR,
    ORIGINAL_VIDEO,
    OUTPUT_IMAGE_FORMAT,
)
from src.files.batch_utils import make_default_batch_dir


def get_fps_accurate(video_path: str) -> float:
    """
    Возвращает среднее количество кадров в секунду для указанного видео.
    :param video_path: Путь к видеофайлу.
    :return: Среднее количество кадров в секунду.
    """
    # Проверяем, что видео доступно и открывается
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise Exception(f"Не удалось открыть видео {video_path}")

    print(f"Файл {video_path} существует и доступен для обработки.")
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    print(f"\tСреднее количество кадров в секунду: {fps}")
    return fps


def compare_strings(string: str) -> int:
    """
    Сравнивает строку с числом в конце имени файла.
    :param string: Строка, содержащая имя файла.
    :return: Число в конце имени файла.
    """
    num = int(string.split("_")[-1]) if "_" in string else int(string)
    return num


def form_frame_name(path_to_frame: str, num: int) -> str:
    """
    Формирует имя файла для указанного номера кадра в таком формате:
        - frame_00000001.jpg
        - frame_00000135.jpg
        - frame_00052672.jpg
    :param path_to_frame: Путь к кадру.
    :param num: Номер кадра.
    :return: Имя файла.
    """
    return os.path.join(path_to_frame, f"frame_{num:08d}.jpg")


def extract_frames_to_batches(
    threads: int,
    video_path: str = ORIGINAL_VIDEO,
    output_dir: str = INPUT_BATCHES_DIR,
    batch_size: int = FRAMES_PER_BATCH,
) -> None:
    """
    Извлекает кадры из видеофайла и сохраняет их по батчам в папках по 1000 кадров.
    :param threads: Количество потоков для извлечения кадров.
    :param video_path: Путь к исходному видеофайлу.
    :param output_dir: Базовая директория для сохранения батчей с кадрами.
    :param batch_size: Количество кадров в одном батче.
    """
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 256)

    print("Извлечение кадров из оригинального видеофайла...")
    with tqdm(
        total=total_frames,
        desc=f"{Fore.GREEN}Фреймов извлечено{Style.RESET_ALL}",
        ncols=150,
        colour="green",
        file=sys.stdout,
    ) as pbar, ThreadPoolExecutor(max_workers=threads) as executor:
        futures = []
        current_batch_dir = make_default_batch_dir(output_dir)

        for frame_num in range(1, total_frames + 1):
            ret, frame = cap.read()
            if not ret:
                break

            frame_path = form_frame_name(current_batch_dir, frame_num)
            futures.append(
                executor.submit(
                    cv2.imwrite, frame_path, frame, [int(cv2.IMWRITE_JPEG_QUALITY), 100]
                )
            )

            if frame_num % batch_size == 0:
                current_batch_dir = make_default_batch_dir(output_dir)
            if len(futures) >= threads * 2:
                for future in as_completed(futures[:threads]):
                    futures.remove(future)
                pbar.update(threads)

        for _ in as_completed(futures):
            pbar.update(1)

    cap.release()
    print("Извлечение завершено.")


def count_total_frames(directory: str) -> int:
    """Считает общее количество фреймов во всех батчах."""
    return sum(len(files) for _, _, files in os.walk(directory) if files)


def count_frames_in_certain_batches(directory: str, batches_num_range: range) -> int:
    """Считает общее количество фреймов в указанных батчах."""
    count = 0
    ext = f".{OUTPUT_IMAGE_FORMAT}"
    for batch_num in batches_num_range:
        batch_dir = os.path.join(directory, f"batch_{batch_num}")
        if os.path.exists(batch_dir):
            count += sum(
                1 for entry in os.scandir(batch_dir) if entry.name.endswith(ext)
            )
    return count
