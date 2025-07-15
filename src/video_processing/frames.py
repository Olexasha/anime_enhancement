import glob
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import cv2
import ffmpeg
from colorama import Fore, Style
from tqdm import tqdm

from src.config.settings import (
    ALLOWED_THREADS,
    FRAMES_PER_BATCH,
    INPUT_BATCHES_DIR,
    ORIGINAL_VIDEO,
    OUTPUT_IMAGE_FORMAT,
)
from src.utils.batch_utils import make_default_batch_dir


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
    # Получаем метаданные видео с помощью ffmpeg
    # metadata = ffmpeg.probe(video_path)
    # duration = float(metadata["format"]["duration"])
    # if duration == 0:
    #     raise ZeroDivisionError("Видео имеет нулевую длительность")
    #
    # # Пытаемся получить количество кадров из метаданных
    # nb_frames = metadata["streams"][0].get("nb_frames")
    # if nb_frames is not None:
    #     print(f"В метаданных видеофайла есть информация о количестве кадров...")
    #     frames = int(nb_frames)
    # else:
    #     # Если информация о количестве кадров отсутствует, считаем их с помощью OpenCV
    #     print(f"Считаем количество кадров с помощью OpenCV...")
    #     frames = 0
    #     while True:
    #         ret, _ = cap.read()
    #         if not ret:
    #             break
    #         frames += 1
    #
    # cap.release()
    # fps = frames / duration
    fps = cap.get(cv2.CAP_PROP_FPS)
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
    video_path: str = ORIGINAL_VIDEO,
    output_dir: str = INPUT_BATCHES_DIR,
    batch_size: int = FRAMES_PER_BATCH,
) -> None:
    """
    Извлекает кадры из видеофайла и сохраняет их по батчам в папках по 1000 кадров.
    :param video_path: Путь к исходному видеофайлу.
    :param output_dir: Базовая директория для сохранения батчей с кадрами.
    :param batch_size: Количество кадров в одном батче.
    """
    video_capture = cv2.VideoCapture(video_path)
    frame_count = 0
    increments = int(video_capture.get(cv2.CAP_PROP_FRAME_COUNT))

    print("Извлечение кадров из оригинального видеофайла...")
    with tqdm(
        total=increments,
        desc=f"{Fore.GREEN}Фреймов извлечено{Style.RESET_ALL}",
        ncols=150,
        colour="green",
        file=sys.stdout,
    ) as pbar:
        with ThreadPoolExecutor(max_workers=ALLOWED_THREADS) as executor:
            current_batch_dir = make_default_batch_dir(output_dir)

            while True:
                ret, frame = video_capture.read()
                if not ret:
                    break

                # Формируем путь для кадра и добавляем задачу на запись кадра
                frame_path = form_frame_name(current_batch_dir, frame_count + 1)
                executor.submit(
                    cv2.imwrite, frame_path, frame, [int(cv2.IMWRITE_JPEG_QUALITY), 100]
                )

                frame_count += 1
                pbar.update(1)  # Обновляем прогресс-бар

                # Если текущий батч заполнен, создаем новый
                if frame_count % batch_size == 0:
                    current_batch_dir = make_default_batch_dir(output_dir)

    video_capture.release()
    print("Извлечение завершено.")


def count_total_frames(directory: str) -> int:
    """Считает общее количество фреймов во всех батчах."""
    return sum(
        len(glob.glob(os.path.join(batch, f"*.{OUTPUT_IMAGE_FORMAT}")))
        for batch in glob.glob(os.path.join(directory, "batch_*"))
    )


def count_frames_in_certain_batches(directory: str, batches_num_range: range) -> int:
    """Считает общее количество фреймов в указанных батчах."""
    frames_in_batches = 0

    for batch_num in batches_num_range:
        batch_dir = os.path.join(directory, f"batch_{batch_num}")
        frames_in_batches += len(
            glob.glob(os.path.join(batch_dir, f"*.{OUTPUT_IMAGE_FORMAT}"))
        )

    return frames_in_batches
