from src.config.settings import OUTPUT_BATCHES_DIR
from src.utils.file_utils import create_dir

batch_counter = 1


def make_default_batch_dir(path: str = OUTPUT_BATCHES_DIR) -> str:
    """
    Создает директорию для батча с дефолтными фреймами.
    :param path: Путь к батчам.
    :return: Созданная директория батча.
    """
    global batch_counter
    batch_name = f"batch_{batch_counter}"
    batch_path = create_dir(path, batch_name)
    batch_counter += 1
    return batch_path
