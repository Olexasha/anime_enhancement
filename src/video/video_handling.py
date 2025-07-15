import glob
import os

import cv2

from src.config.settings import BATCH_VIDEO_PATH, OUTPUT_BATCHES_DIR, TMP_VIDEO
from src.utils.file_utils import delete_file
from src.video.video_helpers import FIFOPriorityQueue


class VideoHandler:
    """
    Класс для сборки и объединения видео из апскейленных фреймов с
    автоматическим управлением очередями объединения.
    """

    def __init__(self, fps: float):
        self.fps = fps
        self.video_queue = FIFOPriorityQueue()

    @staticmethod
    def _build_video_path(video_name: str, path=BATCH_VIDEO_PATH):
        """Генерирует путь к видео с заданным именем."""
        return os.path.join(path, f"{video_name}.mp4")

    @staticmethod
    def _collect_frames(batches_list: list) -> list:
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

    def _generate_video_from_frames(
        self, frame_paths: list, batch_range_start: str, batch_range_end: str
    ) -> str:
        """
        Создает видео из списка фреймов, используя OpenCV.
        :param frame_paths: Список абсолютных путей к фреймам.
        :param batch_range_start: Начальный номер батча для именования видео.
        :param batch_range_end: Конечный номер батча для именования видео.
        :return: Путь к созданному видеофайлу.
        """
        video_path = self._build_video_path(
            f"short_{batch_range_start}-{batch_range_end}"
        )
        print(f"🎥 Начинаем создание видео из {len(frame_paths)} фреймов...")

        # Получаем размер первого кадра для инициализации VideoWriter
        first_frame = cv2.imread(frame_paths[0])
        if first_frame is None:
            raise ValueError(f"🚨 Не удалось прочитать первый кадр: {frame_paths[0]}")
        height, width, _ = first_frame.shape

        # Инициализируем VideoWriter
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(video_path, fourcc, self.fps, (width, height))
        try:
            for i, frame_path in enumerate(frame_paths):
                frame = cv2.imread(frame_path)
                if frame is None:
                    print(f"⚠️ Пропущен кадр (не удалось прочитать): {frame_path}")
                    continue
                out.write(frame)

                # Выводим прогресс каждые 200 кадров
                frame_num = i + 1
                if frame_num % 200 == 0 or frame_num == len(frame_paths):
                    print(f"📹 Обработано кадров: {i + 1}/{len(frame_paths)}")
        finally:
            out.release()

        print(f"✅ Видео успешно создано: {video_path} (FPS: {self.fps})")
        return video_path

    def process_frames_to_video(self, frame_batches: list):
        """
        Собирает обработанные фреймы из батчей в одно короткое видео.
        :param frame_batches: Список имен батчей, из которых нужно собрать фреймы.
        :return: Путь к созданному видеофайлу.
        """
        print(f"\n🔄 Начинаем обработку {len(frame_batches)} батчей фреймов...")
        batch_range_start = frame_batches[0].split("_")[1]
        batch_range_end = frame_batches[-1].split("_")[1]
        frame_paths = self._collect_frames(frame_batches)
        video_path = self._generate_video_from_frames(
            frame_paths, batch_range_start, batch_range_end
        )
        self.video_queue.put((0, video_path))
        print(f"📥 Видео добавлено в очередь: {video_path}")
        return video_path

    def _merge_two_videos(self, first_video: str, second_video: str) -> str:
        """
        Объединяет два видео в одно с помощью OpenCV.
        :param first_video: Путь к первому видеофайлу.
        :param second_video: Путь ко второму видеофайлу.
        :return: Путь к объединенному видеофайлу.
        """
        print(f"\n🔀 Начинаем слияние видео:\n1. {first_video}\n2. {second_video}")
        if not os.path.isfile(first_video):
            raise FileNotFoundError(f"🚨 Видео не найдено: {first_video}")
        if not os.path.isfile(second_video):
            raise FileNotFoundError(f"🚨 Видео не найдено: {second_video}")

        # Создаем объекты VideoCapture для обоих видео
        cap1 = cv2.VideoCapture(first_video)
        cap2 = cv2.VideoCapture(second_video)

        # Проверяем параметры первого видео (они будут использованы для выходного файла)
        width = int(cap1.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap1.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # Создаем имя для объединенного видео
        video_1 = (
            os.path.basename(first_video).split(".")[0].split("_")[-1].split("-")[0]
        )
        video_2 = (
            os.path.basename(second_video).split(".")[0].split("_")[-1].split("-")[-1]
        )
        merged_video_path = self._build_video_path(f"merged_{video_1}-{video_2}")

        # Инициализируем VideoWriter
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(merged_video_path, fourcc, self.fps, (width, height))

        try:
            print("⏳ Обрабатываем первое видео...")
            while cap1.isOpened():
                ret, frame = cap1.read()
                if not ret:
                    break
                out.write(frame)
            print("⏳ Обрабатываем второе видео...")
            while cap2.isOpened():
                ret, frame = cap2.read()
                if not ret:
                    break
                out.write(frame)
            print(f"✅ Видео успешно объединены: {merged_video_path}")
        finally:
            cap1.release()
            cap2.release()
            out.release()

        # Удаляем исходные видеофайлы
        delete_file(first_video)
        delete_file(second_video)
        print(f"🗑️ Исходные видеофайлы удалены")
        return merged_video_path

    def build_final_video(self) -> str | None:
        """Выполняет попарное объединение видео из основной очереди."""
        print("\n🏁 Начинаем финальную сборку видео...")
        print(f"📊 Видео в очереди: {self.video_queue.qsize()}")

        while self.video_queue.qsize() >= 2:
            priority1, video1 = self.video_queue.get()
            priority2, video2 = self.video_queue.get()
            if priority1 < priority2:
                self.video_queue.put((priority1 + 1, video1))
                priority1, video1 = priority2, video2
                priority2, video2 = self.video_queue.get()
            print(f"\n🔧 Объединяем видео с приоритетами {priority1} и {priority2}")
            merged_video = self._merge_two_videos(video1, video2)
            new_priority = max(priority1, priority2) + 1
            self.video_queue.put((new_priority, merged_video))
            print(
                f"📤 Объединенное видео добавлено в очередь с приоритетом {new_priority}"
            )

        if self.video_queue.qsize() == 1:
            _, final_merge = self.video_queue.get()
            os.rename(final_merge, TMP_VIDEO)
            print(f"\n🎉 Финальное видео успешно создано: {TMP_VIDEO}")
            return TMP_VIDEO

        print("🤷 Нет видео для объединения")
        return None
