import shutil
from pathlib import Path
from typing import Optional


def create_dir(path: str, dir_name: str) -> Path:
    """
    Создает директорию с указанным именем в заданном пути.
    :param path: Базовый путь для создания директории.
    :param dir_name: Имя создаваемой директории.
    :return: Путь к созданной директории в виде объекта Path.
    """
    new_dir = Path(path) / dir_name
    new_dir.mkdir(parents=True, exist_ok=True)
    return Path(new_dir)


def delete_dir(dir_path: str) -> None:
    """
    Удаляет указанную директорию и ее содержимое.
    :param dir_path: Путь к директории для удаления.
    """
    dir_path = Path(dir_path)
    if dir_path.exists() and dir_path.is_dir():
        shutil.rmtree(dir_path)
        print(f"Директория {dir_path} удалена.")
    else:
        print(f"Директория {dir_path} не существует.")


def delete_file(file_path: str) -> None:
    """
    Удаляет указанный файл.
    :param file_path: Путь к файлу для удаления.
    """
    file_path = Path(file_path)
    if file_path.exists() and file_path.is_file():
        file_path.unlink()
        print(f"Файл {file_path} удален.")
    else:
        print(f"Файл {file_path} не существует.")


def delete_object(object_path: str) -> None:
    """
    Удаляет объект (файл, директорию или символическую ссылку) по указанному пути.
    :param object_path: Путь к объекту для удаления.
    """
    path = Path(object_path)
    if path.is_dir():
        delete_dir(str(path))
    elif path.is_file() or path.is_symlink():
        delete_file(str(path))
    else:
        print(f"Объект {object_path} не существует или имеет неподдерживаемый тип.")


def copy_object(
    src_path: str, dest_path: str, overwrite: bool = False
) -> Optional[Path]:
    """
    Копирует файл или директорию в указанное место назначения.
    :param src_path: Путь к исходному файлу или директории.
    :param dest_path: Путь к месту назначения.
    :param overwrite: Если True, то перезапишет файлы или директории при необходимости.
    :return: Путь к скопированному объекту или None, если копирование не удалось.
    """
    src = Path(src_path)
    dest = Path(dest_path)

    if not src.exists():
        print(f"Источник {src} не существует.")
        return None

    if dest.exists() and not overwrite:
        print(
            f"Назначение {dest} уже существует. Используйте 'overwrite=True' для перезаписи."
        )
        return None

    try:
        if src.is_dir():
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest)
            print(f"Директория {src} скопирована в {dest}.")
        elif src.is_file():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            print(f"Файл {src} скопирован в {dest}.")
        return dest
    except Exception as e:
        print(f"Ошибка при копировании {src} в {dest}: {e}")
        return None
