from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=128)
def create_dir(path: str, dir_name: str) -> Path:
    """
    Создает директорию с указанным именем в заданном пути.
    :param path: Базовый путь для создания директории.
    :param dir_name: Имя создаваемой директории.
    :return: Путь к созданной директории в виде объекта Path.
    """
    new_dir = Path(path) / dir_name
    new_dir.mkdir(parents=True, exist_ok=True)
    return new_dir
