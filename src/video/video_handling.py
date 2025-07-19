import asyncio
import glob
import os
import time

import cv2

from src.config.settings import BATCH_VIDEO_PATH, OUTPUT_BATCHES_DIR, TMP_VIDEO_PATH
from src.files.file_actions import delete_file
from src.video.video_exceptions import (
    VideoDoesNotExist,
    VideoMergingError,
    VideoReadFrameError,
)
from src.video.video_helpers import FIFOPriorityQueue, sort_video_paths


class VideoHandler:
    """
    Класс для сборки и объединения видео из апскейленных фреймов с
    автоматическим управлением очередями объединения.
    """

    def __init__(self, fps: float):
        self.fps = fps
        self.video_queue = FIFOPriorityQueue()

    async def build_short_video(self, frame_batches: list) -> str:
        """
        Собирает обработанные фреймы из батчей в одно короткое видео.
        :param frame_batches: Список имен батчей, из которых нужно собрать фреймы.
        :return: Путь к созданному видеофайлу.
        """
        print(f"\n🔄 Начинаем обработку {len(frame_batches)} батчей фреймов...")
        batch_range_start = frame_batches[0].split("_")[1]
        batch_range_end = frame_batches[-1].split("_")[1]
        frame_paths = self.__collect_frames(frame_batches)
        video_path = await self._generate_video_from_frames(
            frame_paths, batch_range_start, batch_range_end
        )
        self.video_queue.put((0, video_path))
        print(f"📥 Видео добавлено в очередь: {video_path}")
        return video_path

    def build_final_video(self) -> str | None:
        """
        Собирает все видео из очереди в одно финальное видео.
        :return: Путь к созданному видеофайлу или None, если очередь пуста.
        """
        print("\n🏁 Начинаем финальную сборку видео...")

        video_paths = []
        print(f"\n🔀 Начинаем слияние {len(video_paths)} видео:")
        for i in range(self.video_queue.qsize()):
            video_path = self.video_queue.get()[1]
            if not os.path.isfile(video_path):
                raise VideoDoesNotExist(video_path)
            video_paths.append(video_path)
            print(f"  {i + 1}. {os.path.basename(video_path)}")
        video_paths = sort_video_paths(video_paths)

        if not video_paths:
            raise ValueError("Список видео не может быть пустым")

        output_video = self._handle_merging(video_paths)
        for video_path in video_paths:
            delete_file(video_path)
        return output_video

    async def _generate_video_from_frames(
        self, frame_paths: list, batch_range_start: str, batch_range_end: str
    ) -> str:
        """
        Создает видео из списка фреймов, используя OpenCV.
        :param frame_paths: Список абсолютных путей к фреймам.
        :param batch_range_start: Начальный номер батча для именования видео.
        :param batch_range_end: Конечный номер батча для именования видео.
        :return: Путь к созданному видеофайлу.
        """

        def __generate():
            video_path = self.__build_video_path(
                f"short_{batch_range_start}-{batch_range_end}"
            )
            print(f"🎥 Начинаем создание видео из {len(frame_paths)} фреймов...")

            # Получаем размер первого кадра для инициализации VideoWriter
            first_frame = cv2.imread(frame_paths[0])
            if first_frame is None:
                raise VideoReadFrameError(frame_paths[0])
            height, width, _ = first_frame.shape

            # Инициализируем VideoWriter
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            out = cv2.VideoWriter(video_path, fourcc, self.fps, (width, height))
            try:
                total_frames = len(frame_paths)
                for i, frame_path in enumerate(frame_paths):
                    frame = cv2.imread(frame_path)
                    if frame is None:
                        print(f"⚠️ Пропущен кадр (не удалось прочитать): {frame_path}")
                        continue
                    out.write(frame)

                    # Выводим прогресс каждые 300 кадров
                    frame_num = i + 1
                    if frame_num % 500 == 0 or frame_num == total_frames:
                        print(f"📹 Обработано кадров: {i + 1}/{total_frames}")
            finally:
                out.release()

            print(f"✅ Видео успешно создано: {video_path} (FPS: {self.fps})")
            return video_path

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, __generate)

    def _handle_merging(self, video_paths: list) -> str:
        """
        Обрабатывает объединение видео из списка путей к видеофайлам.
        :param video_paths: Список путей к видеофайлам для объединения.
        :return: Путь к созданному видеофайлу.
        """
        cap = cv2.VideoCapture(video_paths[0])
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()

        first_num = video_paths[0].split("_")[-1].split(".")[0].split("-")[0]
        last_num = video_paths[-1].split("_")[-1].split(".")[0].split("-")[-1]
        output_path = self.__build_video_path(
            f"merged_{first_num}-{last_num}", TMP_VIDEO_PATH
        )

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
            print(
                f"\n✅ Успешно объединено {len(video_paths)} видео "
                f"за {total_time:.1f} сек ({total_frames / total_time:.1f} FPS)"
            )
            print(f"📁 Результат: {os.path.basename(output_path)}")
        except VideoMergingError as e:
            print("🚨 Ошибка при объединении видео:")
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

            print(
                f"\n📹 Обрабатываем видео {video_idx}/{len(video_paths)} "
                f"({video_frames} кадров): {os.path.basename(video_path)}"
            )

            for frame_idx in range(video_frames):
                ret, frame = cap.read()
                if not ret:
                    break
                out.write(frame)
                processed_frames += 1

                # Обновляем прогресс каждые 500 кадров
                if processed_frames % 500 == 0:
                    elapsed = time.time() - start_time
                    fps = processed_frames / elapsed if elapsed > 0 else 0
                    remaining = (
                        (total_frames - processed_frames) / fps if fps > 0 else 0
                    )
                    print(
                        f"\rПрогресс: {processed_frames}/{total_frames} "
                        f"({processed_frames / total_frames:.1%}) | "
                        f"FPS: {fps:.1f} | Осталось: {remaining:.1f}s",
                        end="",
                        flush=True,
                    )
            cap.release()

    @staticmethod
    def __build_video_path(video_name: str, path=BATCH_VIDEO_PATH):
        """Генерирует путь к видео с заданным именем."""
        return os.path.join(path, f"{video_name}.mp4")

    @staticmethod
    def __collect_frames(batches_list: list) -> list:
        """
        Собирает пути фреймов из указанных батчей.
        :param batches_list: Список имен батчей, из которых нужно собрать фреймы.
        :return: Список абсолютных путей к фреймам.
        """
        frame_paths = list()
        for batch in batches_list:
            batch_path = str(os.path.join(OUTPUT_BATCHES_DIR, batch))
            frame_paths.extend(
                sorted(glob.glob(os.path.join(batch_path, "frame*.jpg")))
            )
            print(f"📂 Собрано {len(frame_paths)} фреймов из {len(batches_list)} батчей")
        return frame_paths
