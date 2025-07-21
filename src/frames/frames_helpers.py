import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import cv2
from tqdm import tqdm

from src.config.settings import (
    FRAMES_PER_BATCH,
    INPUT_BATCHES_DIR,
    ORIGINAL_VIDEO,
    OUTPUT_IMAGE_FORMAT,
)
from src.files.batch_utils import make_default_batch_dir
from src.utils.logger import logger


def get_fps_accurate(video_path: str) -> float:
    """
    Возвращает среднее количество кадров в секунду для указанного видео.
    :param video_path: Путь к видеофайлу.
    :return: Среднее количество кадров в секунду.
    """
    # Проверяем, что видео доступно и открывается
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.error(f"Не удалось открыть видео {video_path}")
        raise Exception(f"Не удалось открыть видео {video_path}")

    logger.debug(f"Видео {video_path} доступно для обработки")
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    logger.info(f"Среднее количество кадров в секунду: {fps:.2f}")
    return fps


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

    logger.info(f"Начало извлечения {total_frames} кадров из видео")
    logger.debug(f"Параметры: потоки={threads}, batch_size={batch_size}")

    with tqdm(
        total=total_frames,
        desc="Извлечение фреймов",
        ncols=150,
        file=sys.stdout,
    ) as pbar, ThreadPoolExecutor(max_workers=threads) as executor:
        futures = []
        current_batch_dir = make_default_batch_dir(output_dir)
        logger.debug(f"Создан первый батч: {current_batch_dir}")

        for frame_num in range(1, total_frames + 1):
            ret, frame = cap.read()
            if not ret:
                logger.warning(f"Прервано на кадре {frame_num}")
                break

            frame_path = form_frame_name(current_batch_dir, frame_num)
            futures.append(
                executor.submit(
                    cv2.imwrite, frame_path, frame, [int(cv2.IMWRITE_JPEG_QUALITY), 100]
                )
            )

            if frame_num % batch_size == 0:
                current_batch_dir = make_default_batch_dir(output_dir)
                logger.debug(f"Создан новый батч: {current_batch_dir}")

            if len(futures) >= threads * 2:
                for future in as_completed(futures[:threads]):
                    futures.remove(future)
                pbar.update(threads)

        for _ in as_completed(futures):
            pbar.update(1)

    cap.release()
    logger.success(f"Успешно извлечено {total_frames} кадров")


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
    logger.debug(f"Количество кадров в батчах {batches_num_range}: {count}")
    return count
