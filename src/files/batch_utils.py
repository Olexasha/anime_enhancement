from enum import Enum
from pathlib import Path
from typing import List

from src.config.settings import (
    DENOISED_BATCHES_DIR,
    FRAMES_PER_BATCH,
    INPUT_BATCHES_DIR,
    INTERPOLATED_BATCHES_DIR,
    UPSCALED_BATCHES_DIR,
)
from src.files.file_actions import create_dir, delete_dir, delete_object
from src.utils.logger import logger

batch_counter = 1


class BatchType(Enum):
    """Типы батчей для удаления"""

    DEFAULT = "default"
    DENOISE = "denoise"
    UPSCALE = "upscale"
    INTERPOLATE = "interpolate"


# Маппинг типов батчей на директории
BATCH_TYPE_DIRS = {
    BatchType.DEFAULT: INPUT_BATCHES_DIR,
    BatchType.DENOISE: DENOISED_BATCHES_DIR,
    BatchType.UPSCALE: UPSCALED_BATCHES_DIR,
    BatchType.INTERPOLATE: INTERPOLATED_BATCHES_DIR,
}


def make_default_batch_dir(path: str = UPSCALED_BATCHES_DIR) -> str:
    """
    Создает директорию для батча с дефолтными фреймами.
    :param path: Путь к батчам.
    :return: Созданная директория батча.
    """
    global batch_counter
    batch_name = f"batch_{batch_counter}"
    batch_path = create_dir(path, batch_name)
    batch_counter += 1
    return str(batch_path)


async def delete_frames(
    batch_type: BatchType = None,
    start_batch: int = None,
    end_batch: int = None,
    del_all: bool = False,
    del_only_dirs: bool = True,
) -> None:
    """
    Универсальная функция для удаления фреймов и батчей.
    :param batch_type: Тип батчей для удаления (default, denoise, upscale, interpolate)
    :param start_batch: Начальный номер батча (если None, удаляет все)
    :param end_batch: Конечный номер батча (если None, удаляет только start_batch)
    :param del_all: Если True, удаляет все батчи указанного типа
    :param del_only_dirs: Если True, удаляет только директории, иначе файлы и директории
    """
    if batch_type is None:
        batch_type = BatchType.UPSCALE  # по умолчанию для обратной совместимости

    target_dir = BATCH_TYPE_DIRS[batch_type]
    logger.debug(
        f"Начало удаления {batch_type.value} батчей из {target_dir} "
        f"(start={start_batch}, end={end_batch}, del_all={del_all}, del_only_dirs={del_only_dirs})"
    )

    try:
        target_path = Path(target_dir)
        if not target_path.exists():
            logger.warning(f"Директория с батчами не существует: {target_dir}")
            return

        if del_all:
            # Удаляем все батчи в директории
            items = list(target_path.iterdir())
            logger.info(
                f"Удаление всех {batch_type.value} батчей ({len(items)} директорий)"
            )

            # Удаляем кусочками для производительности
            for chunk in _chunk_items(items, FRAMES_PER_BATCH):
                for item in chunk:
                    if del_only_dirs and item.is_dir():
                        await delete_dir(str(item))
                    elif not del_only_dirs:
                        await delete_object(str(item))
        else:
            # Удаляем конкретные батчи
            if start_batch is None:
                logger.warning("Не указан start_batch для удаления конкретных батчей")
                return

            if end_batch is None:
                end_batch = start_batch

            logger.info(f"Удаление {batch_type.value} батчей {start_batch}-{end_batch}")

            for batch_num in range(start_batch, end_batch + 1):
                batch_path = target_path / f"batch_{batch_num}"
                if batch_path.exists():
                    if del_only_dirs and batch_path.is_dir():
                        await delete_dir(str(batch_path))
                    elif not del_only_dirs:
                        await delete_object(str(batch_path))
                    logger.debug(f"Удален {batch_type.value} батч {batch_num}")
                else:
                    logger.debug(
                        f"{batch_type.value} батч {batch_num} не найден, пропускаем"
                    )

    except Exception as error:
        logger.error(
            f"Ошибка в процессе удаления {batch_type.value} батчей: {str(error)}"
        )
        raise


def _chunk_items(items: List[Path], chunk_size: int) -> List[List[Path]]:
    """Делит фреймы на кусочки (chunk) для более быстрого удаления"""
    return [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]


# Функции-обертки для удобства использования
async def delete_default_batches(start_batch: int, end_batch: int = None) -> None:
    """Удаляет default батчи в указанном диапазоне"""
    await delete_frames(BatchType.DEFAULT, start_batch, end_batch)


async def delete_denoise_batches(start_batch: int, end_batch: int = None) -> None:
    """Удаляет denoise батчи в указанном диапазоне"""
    await delete_frames(BatchType.DENOISE, start_batch, end_batch)


async def delete_upscale_batches(start_batch: int, end_batch: int = None) -> None:
    """Удаляет upscale батчи в указанном диапазоне"""
    await delete_frames(BatchType.UPSCALE, start_batch, end_batch)


async def delete_interpolate_batches(start_batch: int, end_batch: int = None) -> None:
    """Удаляет interpolate батчи в указанном диапазоне"""
    await delete_frames(BatchType.INTERPOLATE, start_batch, end_batch)


async def delete_all_batches(batch_type: BatchType) -> None:
    """Удаляет все батчи указанного типа"""
    await delete_frames(batch_type, del_all=True)
