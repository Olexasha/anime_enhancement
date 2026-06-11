import asyncio
import gc
import glob
import multiprocessing
import os
import subprocess
import time
from fractions import Fraction
from pathlib import Path

import cv2

from src.config.settings import (
    BATCH_VIDEO_PATH,
    ENABLE_INTERPOLATION,
    FRAMES_MULTIPLY_FACTOR,
    INTERMEDIATE_VIDEO_CONTAINER,
    INTERMEDIATE_VIDEO_CRF,
    INTERMEDIATE_VIDEO_ENCODER,
    INTERMEDIATE_VIDEO_PIX_FMT,
    INTERMEDIATE_VIDEO_PRESET,
    INTERPOLATED_BATCHES_DIR,
    KEEP_TEMP_FILES,
    OUTPUT_IMAGE_FORMAT,
    TMP_VIDEO_PATH,
    UPSCALED_BATCHES_DIR,
    VIDEO_CRF,
    VIDEO_ENCODER,
    VIDEO_NVENC_CQ,
    VIDEO_PIX_FMT,
    VIDEO_PRESET,
    VIDEO_TUNE,
)
from src.files.batch_utils import delete_interpolate_batches, delete_upscale_batches
from src.files.file_actions import delete_file
from src.utils.logger import logger
from src.video.video_exceptions import (
    VideoDoesNotExist,
    VideoMergingError,
    VideoReadFrameError,
)
from src.video.video_helpers import sort_frame_paths, sort_video_paths


class VideoHandler:
    """
    Класс для сборки и объединения видео из апскейленных фреймов с
    автоматическим управлением очередями объединения.
    """

    def __init__(self, fps: float, keep_temp_files: bool = KEEP_TEMP_FILES):
        self.fps = self.__calculate_fps_after_ai(fps)
        self.keep_temp_files = keep_temp_files
        self.video_queue = multiprocessing.Queue()
        self.final_videos_same_name = 1

    @staticmethod
    def __calculate_fps_after_ai(fps: float) -> float:
        return fps * FRAMES_MULTIPLY_FACTOR if ENABLE_INTERPOLATION else fps

    @staticmethod
    def _force_memory_cleanup() -> None:
        """Принудительно очищает память."""
        try:
            gc.collect()
            logger.debug("Выполнена принудительная очистка памяти")
        except Exception as e:
            logger.warning(f"Ошибка при очистке памяти: {e}")

    def build_short_video(self, frame_batches: list) -> None:
        logger.debug("Запуск асинхронного сбора короткого видео")
        process = multiprocessing.Process(
            target=build_short_video_sync,
            args=(frame_batches, self.fps, self.video_queue, self.keep_temp_files),
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
        for _ in range(self.video_queue.qsize()):
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
            if not self.keep_temp_files:
                for video_path in video_paths:
                    await delete_file(video_path)
            else:
                logger.info(
                    f"KEEP_TEMP_FILES=true: short-видео сохранены в {BATCH_VIDEO_PATH}"
                )
            return output_video
        except VideoMergingError as error:
            logger.error(f"Ошибка при сборке видео: {str(error)}")
            raise

    @staticmethod
    def generate_video_from_frames(
        frame_paths: list, batch_range_start: str, batch_range_end: str, fps: float
    ) -> str:
        """
        Создает видео из списка кадров через канал rawvideo в ffmpeg.
        :param frame_paths: Список абсолютных путей к фреймам.
        :param batch_range_start: Начальный номер батча для именования видео.
        :param batch_range_end: Конечный номер батча для именования видео.
        :param fps: Частота кадров для выходного видео.
        :return: Путь к созданному видеофайлу.
        """
        video_path = os.path.join(
            BATCH_VIDEO_PATH,
            f"short_{batch_range_start}-{batch_range_end}.{INTERMEDIATE_VIDEO_CONTAINER}",
        )
        Path(BATCH_VIDEO_PATH).mkdir(parents=True, exist_ok=True)
        logger.info(f"Создание видео из {len(frame_paths)} фреймов")

        if not frame_paths:
            raise ValueError("Список кадров для сборки видео пуст")

        first_frame = cv2.imread(frame_paths[0])
        if first_frame is None:
            logger.error(f"Не удалось прочитать первый кадр: {frame_paths[0]}")
            raise VideoReadFrameError(frame_paths[0])
        height, width, _ = first_frame.shape

        process = VideoHandler._start_ffmpeg_raw_writer(
            video_path=video_path,
            width=width,
            height=height,
            fps=fps,
        )
        frame_path = ""
        try:
            total_frames = len(frame_paths)
            last_logged_percent = -5.0
            for i, frame_path in enumerate(frame_paths):
                frame = cv2.imread(frame_path)
                if frame is None:
                    logger.warning(f"Пропущен кадр: {frame_path}")
                    continue
                process.stdin.write(frame.tobytes())

                # Очищаем память каждые 100 кадров для больших видео
                if i % 100 == 0 and i > 0:
                    del frame
                    gc.collect()

                frame_num = i + 1
                progress_percent = frame_num * 100 / total_frames
                if (
                    progress_percent - last_logged_percent >= 5
                    or frame_num == total_frames
                ):
                    logger.info(
                        f"FFmpeg short-видео ({batch_range_start}-{batch_range_end}): "
                        f"{frame_num}/{total_frames} ({progress_percent:.1f}%)"
                    )
                    last_logged_percent = progress_percent
        except cv2.error as e:
            logger.critical(
                f"Ошибка при генерировании short видео {batch_range_start}-{batch_range_end}: {str(e)}"
            )
            raise VideoReadFrameError(frame_path) from e
        finally:
            if process.stdin:
                process.stdin.close()
            return_code = process.wait()
            stderr = ""
            if process.stderr:
                stderr = process.stderr.read().decode("utf-8", errors="replace")
            # Очищаем память после завершения
            gc.collect()
        if return_code != 0:
            raise VideoMergingError(
                f"ffmpeg завершился с кодом {return_code}: {stderr}"
            )
        return video_path

    @staticmethod
    def _start_ffmpeg_raw_writer(
        video_path: str,
        width: int,
        height: int,
        fps: float,
    ) -> subprocess.Popen:
        # fmt: off
        cmd = ["ffmpeg", "-y", "-loglevel", "error"]
        cmd += ["-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{width}x{height}", "-r", VideoHandler._format_ffmpeg_fps(fps), "-i", "-"]
        cmd += ["-an"]
        # fmt: on

        cmd += VideoHandler._intermediate_video_encoder_args()
        if Path(video_path).suffix.lower() == ".mp4":
            cmd += ["-movflags", "+faststart"]
        cmd += [video_path]
        logger.info(f"Запуск кодировщика FFmpeg: {' '.join(cmd)}")
        return subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

    @staticmethod
    def _intermediate_video_encoder_args() -> list[str]:
        """
        Возвращает параметры ffmpeg для временных short-видео.

        Short-видео являются транспортом между PNG/RIFE и финальным encode.
        По умолчанию сохраняем RGB без потерь, чтобы не получить block artifacts
        и YUV-конвертацию до финального кодирования.
        """
        if INTERMEDIATE_VIDEO_ENCODER == "libx264rgb":
            return [
                "-c:v",
                "libx264rgb",
                "-preset",
                INTERMEDIATE_VIDEO_PRESET,
                "-crf",
                str(INTERMEDIATE_VIDEO_CRF),
                "-pix_fmt",
                INTERMEDIATE_VIDEO_PIX_FMT,
            ]
        if INTERMEDIATE_VIDEO_ENCODER == "libx264":
            return [
                "-pix_fmt",
                INTERMEDIATE_VIDEO_PIX_FMT,
                "-color_range",
                "tv",
                "-colorspace",
                "bt709",
                "-color_primaries",
                "bt709",
                "-color_trc",
                "bt709",
                "-c:v",
                "libx264",
                "-preset",
                INTERMEDIATE_VIDEO_PRESET,
                "-crf",
                str(INTERMEDIATE_VIDEO_CRF),
            ]
        if INTERMEDIATE_VIDEO_ENCODER == "ffv1":
            return [
                "-c:v",
                "ffv1",
                "-level",
                "3",
                "-g",
                "1",
                "-pix_fmt",
                INTERMEDIATE_VIDEO_PIX_FMT,
            ]
        raise ValueError(
            f"INTERMEDIATE_VIDEO_ENCODER={INTERMEDIATE_VIDEO_ENCODER} не поддерживается. "
            "Используйте libx264rgb, libx264 или ffv1."
        )

    @staticmethod
    def _format_ffmpeg_fps(fps: float) -> str:
        """
        Возвращает FPS в виде дроби для ffmpeg.

        Десятичное 23.97602398 может дать микроскопический дрейф длительности.
        Дробь 24000/1001 сохраняет длительность точнее и не ускоряет видео.
        """
        if fps <= 0:
            raise ValueError(f"Некорректный FPS: {fps}")
        fraction = Fraction(fps).limit_denominator(1001)
        return f"{fraction.numerator}/{fraction.denominator}"

    @staticmethod
    def collect_video_batches(batches_list: list) -> list:
        """
        Собирает пути фреймов из указанных батчей.
        :param batches_list: Список имен батчей, из которых нужно собрать фреймы.
        :return: Список абсолютных путей к фреймам.
        """
        frame_paths = []
        source_dir = (
            INTERPOLATED_BATCHES_DIR if ENABLE_INTERPOLATION else UPSCALED_BATCHES_DIR
        )
        for batch in batches_list:
            batch_path = str(os.path.join(source_dir, batch))
            frames = sort_frame_paths(
                glob.glob(os.path.join(batch_path, f"*.{OUTPUT_IMAGE_FORMAT}"))
            )
            frame_paths.extend(frames)
            logger.debug(f"Собрано {len(frames)} фреймов из {batch}")
        logger.info(f"Всего собрано {len(frame_paths)} фреймов")
        return frame_paths

    def _handle_merging(self, video_paths: list) -> str:
        """
        Обрабатывает объединение видео из списка путей к видеофайлам с периодической очисткой памяти.
        :param video_paths: Список путей к видеофайлам для объединения.
        :return: Путь к созданному видеофайлу.
        """
        first_num = video_paths[0].split("_")[-1].split(".")[0].split("-")[0]
        last_num = video_paths[-1].split("_")[-1].split(".")[0].split("-")[-1]
        output_path = self.__build_video_path(
            f"merged_{first_num}-{last_num}", TMP_VIDEO_PATH
        )
        Path(TMP_VIDEO_PATH).mkdir(parents=True, exist_ok=True)

        if Path(output_path).exists():
            self.final_videos_same_name += 1
            output_path = (
                f"{output_path.rsplit('.mp4', 1)[0]}_{self.final_videos_same_name}.mp4"
            )

        # Подсчитываем общее количество кадров.
        total_frames = sum(
            int(cv2.VideoCapture(p).get(cv2.CAP_PROP_FRAME_COUNT)) for p in video_paths
        )

        concat_list = Path(TMP_VIDEO_PATH) / f"concat_{first_num}-{last_num}.txt"
        try:
            start_time = time.time()
            self.__merge_videos_with_ffmpeg(
                video_paths,
                output_path,
                concat_list,
                expected_duration=total_frames / max(self.fps, 0.001),
            )
            total_time = time.time() - start_time
            logger.info(
                f"Объединено {len(video_paths)} видео за {total_time:.1f} сек "
                f"({total_frames / total_time:.1f} FPS)"
            )
        except VideoMergingError as e:
            logger.error(f"Ошибка объединения видео: {str(e)}")
            raise VideoMergingError(f"Ошибка при объединении видео: {e}") from e
        finally:
            if not self.keep_temp_files:
                concat_list.unlink(missing_ok=True)
            else:
                logger.info(
                    f"KEEP_TEMP_FILES=true: concat list сохранен: {concat_list}"
                )
            # Очищаем память после завершения
            self._force_memory_cleanup()

        return output_path

    @staticmethod
    def __merge_videos_with_ffmpeg(
        video_paths: list,
        output_path: str,
        concat_list: Path,
        expected_duration: float,
    ) -> None:
        with concat_list.open("w", encoding="utf-8") as file:
            for video_path in video_paths:
                safe_path = str(Path(video_path).resolve()).replace("'", "'\\''")
                file.write(f"file '{safe_path}'\n")

        # fmt: off
        cmd = ["ffmpeg", "-y", "-loglevel", "error"]
        cmd += ["-f", "concat", "-safe", "0", "-i", str(concat_list)]
        cmd += ["-an", "-pix_fmt", VIDEO_PIX_FMT, "-color_range", "tv", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709"]
        if VIDEO_ENCODER == "h264_nvenc":
            cmd += ["-c:v", "h264_nvenc", "-preset", "p7", "-tune", "hq", "-cq", str(VIDEO_NVENC_CQ), "-b:v", "0"]
        elif VIDEO_ENCODER == "libx264":
            cmd += ["-c:v", "libx264", "-preset", VIDEO_PRESET]
            if VIDEO_TUNE:
                cmd += ["-tune", VIDEO_TUNE]
            cmd += ["-crf", str(VIDEO_CRF)]
        else:
            raise ValueError(
                f"VIDEO_ENCODER={VIDEO_ENCODER} не поддерживается. "
                "Используйте libx264 или h264_nvenc."
            )
        cmd += ["-movflags", "+faststart", "-progress", "pipe:1", "-nostats", output_path]
        # fmt: on
        logger.info(f"Склейка коротких видео с финальным encode: {' '.join(cmd)}")
        VideoHandler._run_ffmpeg_with_progress(
            cmd,
            expected_duration=expected_duration,
            desc="FFmpeg финальная сборка видео",
        )

    @staticmethod
    def _run_ffmpeg_with_progress(
        cmd: list[str],
        expected_duration: float,
        desc: str,
    ) -> None:
        duration = max(0.001, expected_duration)
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        last_logged_percent = -5.0
        current_percent = 0.0

        if process.stdout:
            for line in process.stdout:
                key, _, value = line.strip().partition("=")
                if key != "out_time_ms":
                    continue
                try:
                    current_time = max(0.0, int(value) / 1_000_000)
                except ValueError:
                    continue
                current_percent = min(100.0, current_time * 100 / duration)
                if current_percent - last_logged_percent >= 5:
                    logger.info(f"{desc}: {current_percent:.1f}%")
                    last_logged_percent = current_percent

        return_code = process.wait()
        stderr = process.stderr.read() if process.stderr else ""
        if return_code != 0:
            raise VideoMergingError(stderr)

        if current_percent < 100:
            logger.info(f"{desc}: 100.0%")

    @staticmethod
    def __build_video_path(video_name: str, path=BATCH_VIDEO_PATH):
        """Генерирует путь к видео с заданным именем."""
        return os.path.join(path, f"{video_name}.mp4")


def build_short_video_sync(
    frame_batches: list,
    fps: float,
    video_queue: multiprocessing.Queue,
    keep_temp_files: bool = KEEP_TEMP_FILES,
) -> None:
    """
    Запускается в отдельном процессе для сборки короткого видео из кадров без ожидания завершения.
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
        logger.success(f"Short видео создано: {video_path} (FPS: {fps})")
        if not keep_temp_files:
            if ENABLE_INTERPOLATION:
                asyncio.run(
                    delete_interpolate_batches(
                        int(batch_range_start), int(batch_range_end)
                    )
                )
            else:
                asyncio.run(
                    delete_upscale_batches(int(batch_range_start), int(batch_range_end))
                )
        else:
            logger.info(
                "KEEP_TEMP_FILES=true: исходные кадры для short-видео сохранены "
                f"для батчей {batch_range_start}-{batch_range_end}"
            )
    else:
        logger.critical("Не удалось создать видео из фреймов")
        raise VideoReadFrameError("Не удалось создать видео из фреймов")
