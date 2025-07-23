import asyncio
import shutil
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


async def delete_dir(dir_path: str) -> None:
    """
    Удаляет указанную директорию и ее содержимое.
    :param dir_path: Путь к директории для удаления.
    """
    dir_path = Path(dir_path)
    if dir_path.exists() and dir_path.is_dir():
        await asyncio.to_thread(shutil.rmtree, dir_path, ignore_errors=False)


async def delete_file(file_path: str) -> None:
    """
    Удаляет указанный файл.
    :param file_path: Путь к файлу для удаления.
    """
    file_path = Path(file_path)
    if file_path.exists() and file_path.is_file():
        await asyncio.to_thread(file_path.unlink)


async def delete_object(object_path: str) -> None:
    """
    Удаляет объект (файл, директорию или символическую ссылку) по указанному пути.
    :param object_path: Путь к объекту для удаления.
    """
    path = Path(object_path)
    if path.is_dir():
        await delete_dir(str(path))
    elif path.is_file() or path.is_symlink():
        await delete_file(str(path))
