import itertools
import re
from queue import PriorityQueue
from typing import Any, List

import cv2


class FIFOPriorityQueue(PriorityQueue):
    """Класс очереди с приоритетом, реализующий FIFO (First In, First Out) логику."""

    def __init__(self):
        super().__init__()
        self.counter = itertools.count()

    def put(self, item, block: bool = True, timeout: float | None = None) -> None:
        """Добавляет элемент в очередь с приоритетом FIFO."""
        count = next(self.counter)
        super().put((item[0], count, item[1]))  # Используем счетчик для FIFO

    def get(self, block: bool = True, timeout: float | None = None) -> Any:
        """Извлекает элемент с наивысшим приоритетом (FIFO)."""
        if self.empty():
            raise IndexError("Очередь пуста")
        item = super().get()
        return item[0], item[2]  # item[0] - приоритет, item[2] - данные


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
        raise Exception(f"Не удалось открыть видео {video_path}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    duration = frame_count / fps
    cap.release()
    if return_fps_too:
        return duration, fps
    return duration


def sort_video_paths(paths: List[str]) -> List[str]:
    """
    Сортирует список путей к видеофайлам по числовым значениям в их именах.
    :param paths: Список путей к видеофайлам.
    :return: Отсортированный список путей к видеофайлам.
    """
    def __extract_numbers(item: str) -> int:
        path = item
        match = re.search(r"(\d+)-(\d+)\.mp4$", path)
        return int(match.group(1)) if match else 0

    return sorted(paths, key=__extract_numbers)
