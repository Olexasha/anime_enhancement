import re

import cv2

from src.utils.logger import logger

FRAME_NUMBER_PATTERN = re.compile(r"(\d+)(?=\.[^.]+$)")


def get_video_duration(
    video_path: str, return_fps_too: bool = False
) -> float | tuple[float, float]:
    """
    Возвращает продолжительность видео в секундах.

    :param video_path: Путь к видеофайлу.
    :param return_fps_too: Если True, возвращает кортеж (длительность, FPS). По умолчанию False.
    :return: Продолжительность видео в секундах.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.error(f"Не удалось открыть видео {video_path}")
        raise Exception(f"Не удалось открыть видео {video_path}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    duration = frame_count / fps
    cap.release()
    if return_fps_too:
        return duration, fps
    return duration


def sort_video_paths(paths: list[str]) -> list[str]:
    """
    Сортирует список путей к видеофайлам по числовым значениям в их именах.
    :param paths: Список путей к видеофайлам.
    :return: Отсортированный список путей к видеофайлам.
    """

    def __extract_numbers(item: str) -> int:
        path = item
        match = re.search(r"(\d+)-(\d+)\.[^.\\/]+$", path)
        return int(match.group(1)) if match else 0

    return sorted(paths, key=__extract_numbers)


def sort_frame_paths(paths: list[str]) -> list[str]:
    """Сортирует пути кадров по числу в имени файла, а не лексикографически."""

    def __extract_number(item: str) -> tuple[int, str]:
        match = FRAME_NUMBER_PATTERN.search(item)
        return int(match.group(1)) if match else -1, item

    return sorted(paths, key=__extract_number)
