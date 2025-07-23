import asyncio
import glob
import multiprocessing
import os
import time

import cv2

from src.config.settings import BATCH_VIDEO_PATH, OUTPUT_BATCHES_DIR, TMP_VIDEO_PATH
from src.files.file_actions import delete_dir, delete_file
from src.utils.logger import logger
from src.video.video_exceptions import (
    VideoDoesNotExist,
    VideoMergingError,
    VideoReadFrameError,
)
from src.video.video_helpers import sort_video_paths


class VideoHandler:
    """
    Класс для сборки и объединения видео из апскейленных фреймов с
    автоматическим управлением очередями объединения.
    """

    def __init__(self, fps: float):
        self.fps = fps
        self.video_queue = multiprocessing.Queue()

    def build_short_video(self, frame_batches: list) -> None:
        logger.debug("Запуск асинхронного сбора короткого видео")
        process = multiprocessing.Process(
            target=build_short_video_sync,
            args=(frame_batches, self.fps, self.video_queue),
        )
        process.start()

    async def build_final_video(self, total_short_videos) -> str | None:
        """
        Собирает все видео из очереди в одно финальное видео.
        :return: Путь к созданному видеофайлу или None, если очередь пуста.
        """
        while True:
            if self.video_queue.qsize() == total_short_videos:
                break
            logger.info(
                f"Ожидание добавления short видео в очередь (требуется: {total_short_videos}, "
                f"текущее количество: {self.video_queue.qsize()})"
            )
            await asyncio.sleep(30)

        video_paths = []
        for i in range(self.video_queue.qsize()):
            video_path = self.video_queue.get()
            if not os.path.isfile(video_path):
                logger.error(f"Видео не существует: {video_path}")
                raise VideoDoesNotExist(video_path)
            video_paths.append(video_path)

        if not video_paths:
            logger.error("Очередь видео пуста")
            raise ValueError("Список видео не может быть пустым")

        video_paths = sort_video_paths(video_paths)
        logger.debug(
            f"Видео для объединения: {[os.path.basename(p) for p in video_paths]}"
        )

        try:
            output_video = self._handle_merging(video_paths)
            for video_path in video_paths:
                await delete_file(video_path)
            return output_video
        except VideoMergingError as error:
            logger.error(f"Ошибка при сборке видео: {str(error)}")
            raise

    @staticmethod
    def generate_video_from_frames(
            frame_paths: list, batch_range_start: str, batch_range_end: str, fps: float
    ) -> str:
        """
        Создает видео из списка фреймов, используя OpenCV.
        :param frame_paths: Список абсолютных путей к фреймам.
        :param batch_range_start: Начальный номер батча для именования видео.
        :param batch_range_end: Конечный номер батча для именования видео.
        :param fps: Частота кадров для выходного видео.
        :return: Путь к созданному видеофайлу.
        """
        video_path = os.path.join(
            BATCH_VIDEO_PATH, f"short_{batch_range_start}-{batch_range_end}.mp4"
        )
        logger.info(f"Создание видео из {len(frame_paths)} фреймов")

        first_frame = cv2.imread(frame_paths[0])
        if first_frame is None:
            logger.error(f"Не удалось прочитать первый кадр: {frame_paths[0]}")
            raise VideoReadFrameError(frame_paths[0])
        height, width, _ = first_frame.shape
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(
            filename=video_path,
            apiPreference=cv2.CAP_FFMPEG,
            fourcc=fourcc,
            fps=fps,
            frameSize=(width, height),
        )
        frame_path = ""
        try:
            total_frames = len(frame_paths)
            for i, frame_path in enumerate(frame_paths):
                frame = cv2.imread(frame_path)
                if frame is None:
                    logger.warning(f"Пропущен кадр: {frame_path}")
                    continue
                out.write(frame)

                # выводим прогресс каждые 500 кадров
                frame_num = i + 1
                if frame_num % 500 == 0 or frame_num == total_frames:
                    logger.info(
                        f"Генерирование short видео ({batch_range_start}-"
                        f"{batch_range_end}): {i + 1}/{total_frames}"
                    )
        except cv2.error as e:
            logger.critical(
                f"Ошибка при генерировании short видео {batch_range_start}-{batch_range_end}: {str(e)}"
            )
            raise VideoReadFrameError(frame_path)
        finally:
            out.release()
        return video_path

    @staticmethod
    def collect_video_batches(batches_list: list) -> list:
        """
        Собирает пути фреймов из указанных батчей.
        :param batches_list: Список имен батчей, из которых нужно собрать фреймы.
        :return: Список абсолютных путей к фреймам.
        """
        frame_paths = []
        for batch in batches_list:
            batch_path = str(os.path.join(OUTPUT_BATCHES_DIR, batch))
            frames = sorted(glob.glob(os.path.join(batch_path, "frame*.jpg")))
            frame_paths.extend(frames)
            logger.debug(f"Собрано {len(frames)} фреймов из {batch}")
        logger.info(f"Всего собрано {len(frame_paths)} фреймов")
        return frame_paths

    @staticmethod
    async def delete_dirs_async(paths: list) -> None:
        """Асинхронно удаляет файлы с логированием ошибок."""
        from collections import defaultdict
        from pathlib import Path

        dirs_to_delete = defaultdict(set)
        for path in paths:
            _dir_path = str(Path(path).parent)
            dirs_to_delete[_dir_path].add(path)

        async def safe_delete_dir(dir_path: str) -> None:
            try:
                await delete_dir(dir_path)
                logger.debug(f"Директория успешно удалена: {dir_path}")
            except Exception as error:
                logger.error(f"Ошибка при удалении директории {dir_path}: {error}")

        tasks = [safe_delete_dir(dir_path) for dir_path in dirs_to_delete.keys()]
        await asyncio.gather(*tasks)

    def _handle_merging(self, video_paths: list) -> str:
        """
        Обрабатывает объединение видео из списка путей к видеофайлам.
        :param video_paths: Список путей к видеофайлам для объединения.
        :return: Путь к созданному видеофайлу.
        """
        first_num = video_paths[0].split("_")[-1].split(".")[0].split("-")[0]
        last_num = video_paths[-1].split("_")[-1].split(".")[0].split("-")[-1]
        output_path = self.__build_video_path(
            f"merged_{first_num}-{last_num}", TMP_VIDEO_PATH
        )

        cap = cv2.VideoCapture(video_paths[0])
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(
            filename=output_path,
            apiPreference=cv2.CAP_FFMPEG,
            fourcc=fourcc,
            fps=self.fps,
            frameSize=(width, height),
        )
        try:
            total_frames = sum(
                int(cv2.VideoCapture(p).get(cv2.CAP_PROP_FRAME_COUNT))
                for p in video_paths
            )
            start_time = time.time()
            self.__merge_videos(video_paths, out, total_frames, start_time)
            total_time = time.time() - start_time
            logger.info(
                f"Объединено {len(video_paths)} видео за {total_time:.1f} сек "
                f"({total_frames / total_time:.1f} FPS)"
            )
        except VideoMergingError as e:
            logger.error(f"Ошибка объединения видео: {str(e)}")
            raise VideoMergingError(f"Ошибка при объединении видео: {e}")
        finally:
            out.release()

        return output_path

    @staticmethod
    def __merge_videos(
        video_paths: list,
        out: cv2.VideoWriter,
        total_frames: int,
        start_time: float,
    ) -> None:
        """
        Объединяет видео из списка путей к видеофайлам в один выходной файл.
        :param video_paths: Список путей к видеофайлам для объединения.
        :param out: Объект VideoWriter для записи выходного видео.
        :param total_frames: Общее количество кадров для отслеживания прогресса.
        :param start_time: Время начала обработки для расчета FPS и оставшегося времени.
        """
        processed_frames = 0
        for video_idx, video_path in enumerate(video_paths, 1):
            cap = cv2.VideoCapture(video_path)
            video_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

            logger.debug(
                f"Обработка видео {video_idx}/{len(video_paths)} "
                f"({video_frames} кадров): {os.path.basename(video_path)}"
            )

            for frame_idx in range(video_frames):
                ret, frame = cap.read()
                if not ret:
                    break
                out.write(frame)
                processed_frames += 1

                # Обновляем прогресс каждые 1000 кадров
                if processed_frames % 1000 == 0:
                    elapsed = time.time() - start_time
                    fps = processed_frames / elapsed if elapsed > 0 else 0
                    remaining = (
                        (total_frames - processed_frames) / fps if fps > 0 else 0
                    )
                    logger.info(
                        f"Склейка видео: {processed_frames}/{total_frames} "
                        f"({processed_frames / total_frames:.1%}) | "
                        f"Осталось: {remaining:.1f}сек"
                    )
            cap.release()

    @staticmethod
    def __build_video_path(video_name: str, path=BATCH_VIDEO_PATH):
        """Генерирует путь к видео с заданным именем."""
        return os.path.join(path, f"{video_name}.mp4")


def build_short_video_sync(
    frame_batches: list, fps: float, video_queue: multiprocessing.Queue
) -> None:
    """
    Запускается в отдельном процессе для сборки короткого видео из фреймов без ожидания завершения.
    :param frame_batches: Список имен батчей, из которых нужно собрать фреймы.
    :param fps: Частота кадров для выходного видео.
    :param video_queue: Очередь для добавления созданного видео.
    """
    batch_range_start = frame_batches[0].split("_")[1]
    batch_range_end = frame_batches[-1].split("_")[1]
    logger.info(
        f"Начало обработки {len(frame_batches)} батчей "
        f"({batch_range_start}-{batch_range_end})"
    )

    frame_paths = VideoHandler.collect_video_batches(frame_batches)
    video_path = VideoHandler.generate_video_from_frames(
        frame_paths, batch_range_start, batch_range_end, fps
    )

    if video_path:
        video_queue.put(video_path)
        logger.info(f"Видео добавлено в очередь: {video_path}")
        logger.success(f"Видео создано: {video_path} (FPS: {fps})")
        # зачищаем отработанные фреймы (апскейлы и дефолты), удалением директорий
        all_paths_to_delete = frame_paths + [
            path.replace("upscaled_frame_batches", "default_frame_batches")
            for path in frame_paths
        ]
        asyncio.run(VideoHandler.delete_dirs_async(all_paths_to_delete))
    else:
        logger.critical("Не удалось создать видео из фреймов")
        raise VideoReadFrameError("Не удалось создать видео из фреймов")
