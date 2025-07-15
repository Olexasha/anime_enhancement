import itertools
from queue import PriorityQueue
from typing import Any


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
