import os
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from math import ceil
from pathlib import Path

import cv2

from src.config.settings import (
    FRAMES_PER_BATCH,
    INPUT_BATCHES_DIR,
    ORIGINAL_VIDEO,
    OUTPUT_IMAGE_FORMAT,
)
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


def get_total_frame_count(video_path: str = ORIGINAL_VIDEO) -> int:
    """Возвращает количество кадров в видео через OpenCV metadata."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.error(f"Не удалось открыть видео {video_path}")
        raise Exception(f"Не удалось открыть видео {video_path}")
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    if total_frames < 1:
        raise ValueError(f"Не удалось определить количество кадров: {video_path}")
    return total_frames


def calculate_total_batches(
    total_frames: int,
    batch_size: int = FRAMES_PER_BATCH,
) -> int:
    """Считает количество batch_N директорий для заданного числа кадров."""
    if batch_size < 1:
        raise ValueError("batch_size должен быть больше 0")
    return max(1, ceil(total_frames / batch_size))


def form_frame_name(path_to_frame: str, num: int) -> str:
    """
    Формирует имя файла для указанного номера кадра в таком формате:
        - frame_00000001.png
        - frame_00000135.png
        - frame_00052672.png
    :param path_to_frame: Путь к кадру.
    :param num: Номер кадра.
    :return: Имя файла.
    """
    return os.path.join(path_to_frame, f"frame_{num:08d}.{OUTPUT_IMAGE_FORMAT}")


def save_frame(frame_path: str, frame) -> bool:
    """Безопасная запись кадра на диск"""
    try:
        ok = cv2.imwrite(frame_path, frame, [int(cv2.IMWRITE_JPEG_QUALITY), 100])
        if not ok:
            logger.error(f"Ошибка сохранения кадра: {frame_path}")
        return ok
    except Exception as e:
        logger.exception(f"Исключение при сохранении кадра {frame_path}: {e}")
        return False


def _batch_num_for_frame(frame_num: int, batch_size: int) -> int:
    return ((frame_num - 1) // batch_size) + 1


def _make_batch_dir(output_dir: str, batch_num: int) -> Path:
    batch_dir = Path(output_dir) / f"batch_{batch_num}"
    batch_dir.mkdir(parents=True, exist_ok=True)
    return batch_dir


def extract_frame_batches_range(
    threads: int,
    start_batch: int,
    end_batch: int,
    video_path: str = ORIGINAL_VIDEO,
    output_dir: str = INPUT_BATCHES_DIR,
    batch_size: int = FRAMES_PER_BATCH,
) -> int:
    """
    Извлекает только нужный диапазон batch_N директорий.

    Это снижает пик диска: default frames будущих окон не лежат на диске,
    пока текущие батчи проходят AI-стадии.
    """
    if start_batch < 1:
        raise ValueError("start_batch должен быть не меньше 1")
    if end_batch < start_batch:
        raise ValueError("end_batch не может быть меньше start_batch")

    total_frames = get_total_frame_count(video_path)
    start_frame = (start_batch - 1) * batch_size + 1
    end_frame = min(end_batch * batch_size, total_frames)
    if start_frame > total_frames:
        logger.warning(
            f"Диапазон батчей {start_batch}-{end_batch} вне видео "
            f"({total_frames} кадров), извлечение пропущено"
        )
        return 0

    workers = max(1, threads)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.error(f"Не удалось открыть видео {video_path}")
        raise Exception(f"Не удалось открыть видео {video_path}")
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 256)
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame - 1)

    total_to_extract = end_frame - start_frame + 1
    logger.info(
        f"Начало windowed-извлечения кадров {start_frame}-{end_frame} "
        f"для батчей {start_batch}-{end_batch} ({total_to_extract} кадров)"
    )
    logger.debug(f"Параметры: threads={workers}, batch_size={batch_size}")

    pending = set()
    saved_frames = 0
    submitted_frames = 0
    last_logged_percent = -5.0
    current_batch_num = 0
    current_batch_dir = Path(output_dir)

    def collect_done(done_futures) -> None:
        nonlocal saved_frames, last_logged_percent
        for future in done_futures:
            if future.result():
                saved_frames += 1
        progress_percent = saved_frames * 100 / max(1, total_to_extract)
        if (
            progress_percent - last_logged_percent >= 5
            or saved_frames == total_to_extract
        ):
            logger.info(
                f"Извлечение фреймов: {saved_frames}/{total_to_extract} "
                f"({progress_percent:.1f}%)"
            )
            last_logged_percent = progress_percent

    try:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            for frame_num in range(start_frame, end_frame + 1):
                ret, frame = cap.read()
                if not ret:
                    logger.warning(f"Прервано на кадре {frame_num}")
                    break

                batch_num = _batch_num_for_frame(frame_num, batch_size)
                if batch_num != current_batch_num:
                    current_batch_num = batch_num
                    current_batch_dir = _make_batch_dir(output_dir, batch_num)
                    logger.debug(f"Создан batch: {current_batch_dir}")

                frame_path = form_frame_name(str(current_batch_dir), frame_num)
                pending.add(executor.submit(save_frame, frame_path, frame))
                submitted_frames += 1

                if len(pending) >= workers * 2:
                    done, pending = wait(pending, return_when=FIRST_COMPLETED)
                    collect_done(done)

            if pending:
                done, _pending = wait(pending)
                collect_done(done)
    finally:
        cap.release()

    if saved_frames != submitted_frames:
        raise RuntimeError(
            f"Не все кадры были сохранены: {saved_frames}/{submitted_frames}"
        )

    logger.success(
        f"Успешно извлечено {saved_frames} кадров для батчей {start_batch}-{end_batch}"
    )
    return saved_frames


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
    total_frames = get_total_frame_count(video_path)
    total_batches = calculate_total_batches(total_frames, batch_size)
    extract_frame_batches_range(
        threads=threads,
        start_batch=1,
        end_batch=total_batches,
        video_path=video_path,
        output_dir=output_dir,
        batch_size=batch_size,
    )


def count_frames_in_certain_batches(
    directory: str, batches_num_range: range = None, just_one_batch: int = 0
) -> int:
    """Считает общее количество фреймов в указанных батчах."""
    count = 0
    ext = f".{OUTPUT_IMAGE_FORMAT}"

    if just_one_batch:
        target_batches = [just_one_batch]
        log_message = f"Количество кадров в батче batch_{just_one_batch}: {{}}"
    else:
        target_batches = batches_num_range
        log_message = f"Количество кадров в батчах {batches_num_range}: {{}}"

    for batch_num in target_batches:
        batch_dir = Path(directory) / f"batch_{batch_num}"
        if not batch_dir.exists():
            continue

        count += sum(
            1
            for entry in os.scandir(batch_dir)
            if entry.is_file() and entry.name.endswith(ext)
        )

    logger.debug(log_message.format(count))
    return count
