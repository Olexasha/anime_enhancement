import asyncio
import gc
import glob
import multiprocessing
import os
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from queue import Empty

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
)
from src.utils.cleanup import (
    CleanupSummary,
    maybe_cleanup_after_stage,
    verify_video_readable,
)
from src.utils.logger import logger
from src.video.video_exceptions import (
    VideoDoesNotExist,
    VideoMergingError,
    VideoReadFrameError,
)
from src.video.video_helpers import sort_frame_paths, sort_video_paths


def _format_duration(seconds: float) -> str:
    total_seconds = max(0, int(round(seconds)))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


@dataclass(slots=True)
class ShortVideoBuildFailure:
    batch_range: str
    message: str


class VideoHandler:
    """
    Класс для сборки и объединения видео из апскейленных фреймов с
    автоматическим управлением очередями объединения.
    """

    def __init__(
        self,
        fps: float,
        keep_temp_files: bool = KEEP_TEMP_FILES,
        max_short_video_builders: int = 2,
    ):
        self.fps = self.__calculate_fps_after_ai(fps)
        self.keep_temp_files = keep_temp_files
        self.max_short_video_builders = max(1, max_short_video_builders)
        self.video_queue = multiprocessing.Queue()
        self.final_videos_same_name = 1
        self.short_video_processes: list[multiprocessing.Process] = []
        self.short_video_results: list = []
        self.short_video_errors: list[ShortVideoBuildFailure] = []
        self.expected_short_video_paths: dict[Path, float] = {}
        self.short_videos_requested = 0
        self.cleanup_summaries: list[CleanupSummary] = []

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
        self._wait_for_short_video_slot()
        logger.debug("Запуск асинхронного сбора короткого видео")
        expected_path = self._expected_short_video_path(frame_batches)
        self.expected_short_video_paths[expected_path] = time.time()
        process = multiprocessing.Process(
            target=build_short_video_sync,
            args=(frame_batches, self.fps, self.video_queue, self.keep_temp_files),
        )
        process.start()
        self.short_video_processes.append(process)
        self.short_videos_requested += 1

    @staticmethod
    def _expected_short_video_path(frame_batches: list) -> Path:
        batch_range_start = frame_batches[0].split("_")[1]
        batch_range_end = frame_batches[-1].split("_")[1]
        return Path(BATCH_VIDEO_PATH) / (
            f"short_{batch_range_start}-{batch_range_end}."
            f"{INTERMEDIATE_VIDEO_CONTAINER}"
        )

    def _wait_for_short_video_slot(self) -> None:
        self._drain_short_video_queue()
        self._collect_finished_short_video_processes()
        while (
            self._active_short_video_processes_count() >= self.max_short_video_builders
        ):
            oldest = next(
                process for process in self.short_video_processes if process.is_alive()
            )
            logger.info(
                "Ожидание свободного short-video builder "
                f"(лимит: {self.max_short_video_builders})"
            )
            oldest.join(timeout=5)
            self._drain_short_video_queue()
            self._collect_finished_short_video_processes()

    def _drain_short_video_queue(self) -> int:
        drained = 0
        while True:
            try:
                queue_item = self.video_queue.get_nowait()
                if isinstance(queue_item, ShortVideoBuildFailure):
                    self.short_video_errors.append(queue_item)
                else:
                    self.short_video_results.append(queue_item)
                drained += 1
            except Empty:
                break
        return drained

    def _raise_short_video_errors(self) -> None:
        if not self.short_video_errors:
            return
        details = "\n".join(
            f"{error.batch_range}: {error.message}" for error in self.short_video_errors
        )
        self.short_video_errors.clear()
        raise VideoMergingError(f"Ошибка short-video builder:\n{details}")

    def check_short_video_builders(self) -> None:
        self._drain_short_video_queue()
        self._collect_finished_short_video_processes()
        self._raise_short_video_errors()

    @staticmethod
    def _short_video_result_path(queue_item) -> Path:
        if isinstance(queue_item, tuple) and len(queue_item) == 2:
            video_path = queue_item[0]
        else:
            video_path = queue_item
        return Path(video_path)

    def _recover_finished_short_videos_from_disk(self) -> int:
        known_paths = {
            self._short_video_result_path(queue_item).resolve()
            for queue_item in self.short_video_results
        }
        recovered = 0
        for expected_path, requested_at in self.expected_short_video_paths.items():
            resolved = expected_path.resolve()
            if resolved in known_paths or not expected_path.is_file():
                continue
            try:
                modified_at = expected_path.stat().st_mtime
            except OSError:
                continue
            if modified_at + 2 < requested_at:
                continue
            if not verify_video_readable(str(expected_path)):
                continue
            self.short_video_results.append(str(expected_path))
            known_paths.add(resolved)
            recovered += 1
            logger.warning(
                "Short-видео найдено на диске, но не было получено из "
                f"multiprocessing queue: {expected_path}"
            )
        return recovered

    def _active_short_video_processes_count(self) -> int:
        return sum(1 for process in self.short_video_processes if process.is_alive())

    def _collect_finished_short_video_processes(self) -> None:
        active_processes: list[multiprocessing.Process] = []
        failed_exit_codes: list[int] = []
        for process in self.short_video_processes:
            if process.is_alive():
                active_processes.append(process)
                continue
            process.join(timeout=0)
            if process.exitcode not in {0, None}:
                failed_exit_codes.append(process.exitcode)
        self.short_video_processes = active_processes
        self._raise_short_video_errors()
        if failed_exit_codes:
            raise VideoMergingError(
                "Процесс short-video завершился с кодом "
                + ", ".join(str(code) for code in failed_exit_codes)
            )

    async def _wait_for_short_video_results(
        self,
        total_short_videos: int,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> None:
        last_reported = -1
        last_logged_wait_state: tuple[int, int] | None = None
        last_logged_wait_at = 0.0
        while True:
            self._drain_short_video_queue()
            self._collect_finished_short_video_processes()
            ready_count = len(self.short_video_results)
            active_count = len(self.short_video_processes)
            if progress_callback is not None and ready_count != last_reported:
                progress_callback(ready_count, total_short_videos)
                last_reported = ready_count
            if ready_count >= total_short_videos and not self.short_video_processes:
                return
            if not self.short_video_processes:
                recovered = self._recover_finished_short_videos_from_disk()
                if recovered:
                    ready_count = len(self.short_video_results)
                    if progress_callback is not None and ready_count != last_reported:
                        progress_callback(ready_count, total_short_videos)
                        last_reported = ready_count
                    if ready_count >= total_short_videos:
                        return
                missing = max(0, total_short_videos - len(self.short_video_results))
                expected = "\n".join(
                    str(path)
                    for path in self.expected_short_video_paths
                    if not path.is_file()
                )
                raise VideoMergingError(
                    f"Не получены результаты short-видео: не хватает {missing} "
                    f"из {total_short_videos}, активных builder-процессов нет."
                    + (
                        f"\nОжидаемые отсутствующие файлы:\n{expected}"
                        if expected
                        else ""
                    )
                )
            wait_state = (ready_count, active_count)
            now = time.monotonic()
            should_log_wait = (
                wait_state != last_logged_wait_state or now - last_logged_wait_at >= 30
            )
            if should_log_wait:
                logger.info(
                    f"Ожидание short-видео (требуется: {total_short_videos}, "
                    f"готово: {ready_count}, "
                    f"активно: {active_count})"
                )
                last_logged_wait_state = wait_state
                last_logged_wait_at = now
            await asyncio.sleep(5)

    async def build_final_video(
        self,
        total_short_videos,
        short_video_progress_callback: Callable[[int, int], None] | None = None,
    ) -> str | None:
        """
        Собирает все видео из очереди в одно финальное видео.
        :return: Путь к созданному видеофайлу или None, если очередь пуста.
        """
        await self._wait_for_short_video_results(
            total_short_videos,
            progress_callback=short_video_progress_callback,
        )

        video_paths = []
        queue_items = self.short_video_results[:total_short_videos]
        self.short_video_results = self.short_video_results[total_short_videos:]
        for queue_item in queue_items:
            cleanup_summary = None
            if isinstance(queue_item, tuple) and len(queue_item) == 2:
                video_path, cleanup_summary = queue_item
            else:
                video_path = queue_item
            if not os.path.isfile(video_path):
                logger.error(f"Видео не существует: {video_path}")
                raise VideoDoesNotExist(video_path)
            if cleanup_summary is not None:
                self.cleanup_summaries.append(cleanup_summary)
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
            self.cleanup_summaries.append(
                await asyncio.to_thread(
                    maybe_cleanup_after_stage,
                    stage="Финальная сборка",
                    paths=video_paths,
                    reason="merged-видео успешно создано, удаляем short-видео",
                    keep_temp_files=self.keep_temp_files,
                    dependency_path=output_video,
                    dependency_is_video=True,
                )
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
        logger.info(f"Создание видео из {len(frame_paths)} кадров")

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
        ffmpeg_write_error: BaseException | None = None
        frame_read_error: cv2.error | None = None
        return_code: int | None = None
        stderr = ""
        try:
            total_frames = len(frame_paths)
            last_logged_percent = -5.0
            for i, frame_path in enumerate(frame_paths):
                if process.poll() is not None:
                    ffmpeg_write_error = RuntimeError(
                        f"ffmpeg завершился до записи кадра {i + 1}/{total_frames}"
                    )
                    break
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
            frame_read_error = e
        except (BrokenPipeError, OSError) as e:
            logger.critical(
                "FFmpeg преждевременно закрыл stdin при сборке short видео "
                f"{batch_range_start}-{batch_range_end}: {e}"
            )
            ffmpeg_write_error = e
        finally:
            if process.stdin:
                try:
                    process.stdin.close()
                except (BrokenPipeError, OSError) as e:
                    if ffmpeg_write_error is None:
                        ffmpeg_write_error = e
            return_code = process.wait()
            if process.stderr:
                stderr = process.stderr.read().decode("utf-8", errors="replace")
            # Очищаем память после завершения
            gc.collect()
        if frame_read_error is not None:
            raise VideoReadFrameError(frame_path) from frame_read_error
        if ffmpeg_write_error is not None:
            reason = stderr.strip() or str(ffmpeg_write_error)
            raise VideoMergingError(
                "ffmpeg преждевременно завершил сборку short-видео "
                f"{batch_range_start}-{batch_range_end}"
                + (f" на кадре {frame_path}" if frame_path else "")
                + f": {reason}"
            ) from ffmpeg_write_error
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
        logger.debug(f"Запуск кодировщика FFmpeg: {' '.join(cmd)}")
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
        Production path использует libx264/yuv444p CRF master, который
        затем попадает в final через stream-copy.
        """
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
                "-tune",
                "animation",
                "-crf",
                str(INTERMEDIATE_VIDEO_CRF),
            ]
        raise ValueError(
            f"INTERMEDIATE_VIDEO_ENCODER={INTERMEDIATE_VIDEO_ENCODER} не поддерживается. "
            "Используйте libx264."
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
        logger.info(f"Всего собрано {len(frame_paths)} кадров")
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
        expected_duration = total_frames / max(self.fps, 0.001)

        concat_list = Path(TMP_VIDEO_PATH) / f"concat_{first_num}-{last_num}.txt"
        merge_succeeded = False
        try:
            start_time = time.time()
            self.__merge_videos_with_ffmpeg(
                video_paths,
                output_path,
                concat_list,
                expected_duration=expected_duration,
                fps=self.fps,
            )
            total_time = time.time() - start_time
            logger.info(
                f"Объединено {len(video_paths)} видео за {total_time:.1f} сек "
                f"({total_frames / total_time:.1f} FPS)"
            )
            if not verify_video_readable(
                output_path,
                min_duration=max(0.001, expected_duration * 0.95),
            ):
                raise VideoMergingError(
                    f"merged-видео не прошло проверку ffprobe: {output_path}"
                )
            merge_succeeded = True
        except VideoMergingError as e:
            logger.error(f"Ошибка объединения видео: {str(e)}")
            raise VideoMergingError(f"Ошибка при объединении видео: {e}") from e
        finally:
            if merge_succeeded:
                self.cleanup_summaries.append(
                    maybe_cleanup_after_stage(
                        stage="Финальная сборка",
                        paths=[concat_list],
                        reason="merged-видео создано, удаляем concat list",
                        keep_temp_files=self.keep_temp_files,
                        dependency_path=output_path,
                        dependency_is_video=True,
                    )
                )
            else:
                logger.warning(
                    "Пропуск удаления: итоговый merged-файл не прошел проверку, "
                    f"concat list сохранен: {concat_list}"
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
        fps: float,
    ) -> None:
        with concat_list.open("w", encoding="utf-8") as file:
            for video_path in video_paths:
                safe_path = str(Path(video_path).resolve()).replace("'", "'\\''")
                file.write(f"file '{safe_path}'\n")

        VideoHandler.__merge_videos_with_stream_copy(
            output_path,
            concat_list,
            expected_duration=expected_duration,
            fps=fps,
        )

    @staticmethod
    def __merge_videos_with_stream_copy(
        output_path: str,
        concat_list: Path,
        expected_duration: float,
        fps: float,
    ) -> None:
        track_timescale = Fraction(fps).limit_denominator(1001).numerator
        # fmt: off
        cmd = ["ffmpeg", "-y", "-loglevel", "error"]
        cmd += ["-f", "concat", "-safe", "0", "-i", str(concat_list)]
        cmd += ["-an", "-c:v", "copy", "-movflags", "+faststart"]
        cmd += ["-video_track_timescale", str(track_timescale)]
        cmd += ["-progress", "pipe:1", "-nostats", output_path]
        # fmt: on
        logger.debug(
            f"Склейка short-видео без повторного video encode: {' '.join(cmd)}"
        )
        VideoHandler._run_ffmpeg_with_progress(
            cmd,
            expected_duration=expected_duration,
            desc="FFmpeg stream-copy сборка видео",
        )

    @staticmethod
    def _run_ffmpeg_with_progress(
        cmd: list[str],
        expected_duration: float,
        desc: str,
    ) -> None:
        duration = max(0.001, expected_duration)
        started_at = time.time()
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
                if current_percent < 100 and current_percent - last_logged_percent >= 5:
                    logger.info(f"{desc}: {current_percent:.1f}%")
                    last_logged_percent = current_percent

        return_code = process.wait()
        stderr = process.stderr.read() if process.stderr else ""
        if return_code != 0:
            raise VideoMergingError(stderr)

        logger.success(
            f"{desc}: завершено за {_format_duration(time.time() - started_at)}"
        )

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

    try:
        frame_paths = VideoHandler.collect_video_batches(frame_batches)
        video_path = VideoHandler.generate_video_from_frames(
            frame_paths, batch_range_start, batch_range_end, fps
        )

        if video_path and verify_video_readable(video_path):
            cleanup_source_dir = (
                INTERPOLATED_BATCHES_DIR
                if ENABLE_INTERPOLATION
                else UPSCALED_BATCHES_DIR
            )
            cleanup_source_name = (
                "RIFE-кадры" if ENABLE_INTERPOLATION else "upscaled frames"
            )
            cleanup_paths = [
                Path(cleanup_source_dir) / f"batch_{batch_num}"
                for batch_num in range(int(batch_range_start), int(batch_range_end) + 1)
            ]
            cleanup_summary = maybe_cleanup_after_stage(
                stage=f"Батч {batch_range_start}-{batch_range_end}",
                paths=cleanup_paths,
                reason=f"short-video успешно создан, удаляем {cleanup_source_name} батча",
                keep_temp_files=keep_temp_files,
                dependency_path=video_path,
                dependency_is_video=True,
            )
            video_queue.put((video_path, cleanup_summary))
            logger.info(f"Видео добавлено в очередь: {video_path}")
            logger.success(f"Short видео создано: {video_path} (FPS: {fps})")
        else:
            logger.critical(
                "Не удалось создать читаемое short-video из фреймов; "
                "предыдущие кадры не удаляются"
            )
            raise VideoReadFrameError(
                "Не удалось создать читаемое short-video из фреймов"
            )
    except Exception as error:
        batch_range = f"{batch_range_start}-{batch_range_end}"
        message = str(error)
        try:
            video_queue.put(
                ShortVideoBuildFailure(batch_range=batch_range, message=message)
            )
        except Exception as queue_error:
            logger.error(
                "Не удалось передать ошибку short-video builder в очередь: "
                f"{queue_error}"
            )
        logger.critical(f"Short-video {batch_range} не создан: {message}")
        raise
