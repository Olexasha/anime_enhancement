import glob
import os
from queue import PriorityQueue

import ffmpeg
from moviepy import VideoFileClip, concatenate_videoclips

from src.config.settings import BATCH_VIDEO_PATH, OUTPUT_BATCHES_DIR, TMP_VIDEO
from src.utils.file_utils import delete_file


class VideoHandler:
    """
    Класс для сборки и объединения видео из апскейленных фреймов с
    автоматическим управлением очередями объединения.
    """

    def __init__(self, fps: float):
        self.fps = fps
        self.curr_short_video_count = 0
        self.video_queue = PriorityQueue()

    @staticmethod
    def _build_video_path(video_name, path=BATCH_VIDEO_PATH):
        """Генерирует путь к видео с заданным именем."""
        return os.path.join(path, f"{video_name}.mp4")

    @staticmethod
    def _collect_frames(batches_list):
        """Собирает пути фреймов из указанных батчей."""
        frame_paths = []
        for batch in batches_list:
            batch_path = str(os.path.join(OUTPUT_BATCHES_DIR, batch))
            frame_paths.extend(
                sorted(glob.glob(os.path.join(batch_path, "frame*.jpg")))
            )
        return frame_paths

    @staticmethod
    def _create_frames_file(frame_paths):
        """Создает временный файл со списком фреймов для ffmpeg."""
        frames_file_path = os.path.join("./", "frames_list.txt")
        with open(frames_file_path, "w") as file:
            for frame in frame_paths:
                file.write(f"file '{frame}'\n")
        return frames_file_path

    def _generate_video_from_frames(
        self, frames_file_path, batch_range_start, batch_range_end
    ):
        """Создает видео из списка фреймов, используя ffmpeg."""
        video_path = self._build_video_path(
            f"short_{batch_range_start}-{batch_range_end}"
        )
        ffmpeg.input(frames_file_path, format="concat", safe=0).output(
            video_path, vcodec="libx264", pix_fmt="yuv420p", crf=18, r=self.fps
        ).run()
        self.curr_short_video_count += 1
        return video_path

    def process_frames_to_video(self, frame_batches: list):
        """Собирает обработанные фреймы из батчей в одно короткое видео."""
        batch_range_start = frame_batches[0].split("_")[1]
        batch_range_end = frame_batches[-1].split("_")[1]
        frame_paths = self._collect_frames(frame_batches)
        frames_file_path = self._create_frames_file(frame_paths)

        video_path = self._generate_video_from_frames(
            frames_file_path, batch_range_start, batch_range_end
        )
        delete_file(frames_file_path)  # Удаляем временный файл списка фреймов

        self.video_queue.put(
            (0, video_path)
        )  # Добавляем видео в очередь с макс приоритетом
        return video_path

    def _merge_two_videos(self, first_video, second_video):
        """Объединяет два видео в одно."""
        if os.path.isfile(first_video) and os.path.isfile(second_video):
            with VideoFileClip(first_video) as clip1, VideoFileClip(
                second_video
            ) as clip2:
                combined_clip = concatenate_videoclips([clip1, clip2])
                video_1 = os.path.basename(first_video).split(".")[0].split("_")[-1]
                video_2 = os.path.basename(second_video).split(".")[0].split("_")[-1]
                merged_video_path = self._build_video_path(
                    f"merged_{video_1}_{video_2}"
                )
                combined_clip.write_videofile(
                    merged_video_path, codec="libx264", fps=self.fps
                )
                print(f"Слияние видеофайлов завершено: {merged_video_path}")

            delete_file(first_video)
            delete_file(second_video)
            return merged_video_path
        else:
            raise FileNotFoundError(
                f"Не удается найти одно из видео: {first_video} или {second_video}"
            )

    def build_final_video(self):
        """Выполняет попарное объединение видео из основной очереди."""
        while self.video_queue.qsize() >= 2:
            # если количество видео "побольше" в очереди больше 2х, то объединяем их и
            # кладём в очередь. Повторяем до тех пор, пока не останется лишь 1 tmp видео
            priority1, video1 = self.video_queue.get()
            priority2, video2 = self.video_queue.get()
            merged_video = self._merge_two_videos(video1, video2)
            new_priority = max(priority1, priority2) + 1
            self.video_queue.put((new_priority, merged_video))

        if self.video_queue.qsize() == 1:
            # если в длинной очереди осталось лишь 1 видео, то отдаем видео и путь к нему
            _, final_merge = self.video_queue.get()
            os.rename(final_merge, TMP_VIDEO)
            print(f"Финальное видео создано: {TMP_VIDEO}")
            return TMP_VIDEO
        return None

    def __str__(self):
        """Возвращает количество видео в очередях."""
        return f"Количество видео в очереди: {self.video_queue.qsize()}"

    def __repr__(self):
        """Возвращает количество видео в очередях."""
        return self.__str__()
