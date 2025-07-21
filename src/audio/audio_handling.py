import asyncio
import os
import subprocess
from concurrent.futures import ProcessPoolExecutor
from typing import Optional

from src.audio.audio_helpers import run_ffmpeg_command_with_progress
from src.config.settings import (
    AUDIO_PATH,
    FINAL_VIDEO,
    ORIGINAL_VIDEO,
    RESOLUTION,
    TMP_VIDEO_PATH,
)
from src.files.file_actions import delete_file
from src.utils.logger import logger
from src.video.video_helpers import get_video_duration


class AudioHandler:
    """
    Класс для обработки аудио: извлечение аудио из видео и добавление аудио к видео.
    """

    CANALS = "2"  # Стерео
    SAMPLE_FREQ = "44100"  # Частота дискретизации
    BITRATE = "192k"  # Битрейт аудио

    def __init__(
        self,
        threads: int,
        input_video_path: str = ORIGINAL_VIDEO,
        merged_video_path: str = TMP_VIDEO_PATH,
        output_video_path: str = FINAL_VIDEO,
        audio_path: str = AUDIO_PATH,
        audio_format: str = "mp3",
        resolution: str = RESOLUTION,
    ):
        self.threads = threads
        self.in_video_path = input_video_path
        self.tmp_video_path = merged_video_path
        self.out_video_path = output_video_path
        self.audio_path = audio_path
        self.audio_format = audio_format
        self.resolution = resolution
        self.codec = "libmp3lame" if self.audio_format == "mp3" else self.audio_format

        logger.info(
            "Инициализация AudioHandler с параметрами:"
            f"\n\tКодек: {self.codec}"
            f"\n\tБитрейт: {self.BITRATE}"
            f"\n\tЧастота дискретизации: {self.SAMPLE_FREQ} Hz"
            f"\n\tКаналы: {self.CANALS} (стерео)"
            f"\n\tПотоки: {self.threads}"
        )

    def extract_audio_sync(self) -> Optional[str]:
        """
        Извлекает аудио из видеофайла и сохраняет его как отдельный аудиофайл.
        """
        audio_file = self.get_audio_full_path()
        logger.debug(f"Извлечение аудио из {self.in_video_path} в {audio_file}")

        ffmpeg_args = [
            "-y", "-i", self.in_video_path,
            "-vn", "-acodec", self.codec,
            "-ar", self.SAMPLE_FREQ, "-ac", self.CANALS,
            "-b:a", self.BITRATE, "-threads", str(self.threads),
            "-loglevel", "error", audio_file,
        ]
        try:
            result = subprocess.run(
                ["ffmpeg", *ffmpeg_args],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"Ошибка извлечения аудио (FFmpeg): {result.stderr.decode()}"
                )
            self.__check_audio_extracted(audio_file)
            self.audio_path = audio_file
            logger.success(f"Аудио успешно извлечено {audio_file}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Ошибка извлечения аудио: {e.stderr.decode()}")
            raise RuntimeError(f"Ошибка извлечения аудио: {e.stderr.decode()}")

    async def extract_audio(self) -> Optional[str]:
        """Асинхронный запуск извлечения аудио"""
        logger.debug("Запуск асинхронного извлечения аудио")
        loop = asyncio.get_running_loop()
        with ProcessPoolExecutor() as pool:
            return await loop.run_in_executor(pool, self.extract_audio_sync)

    def insert_audio(self) -> None:
        """
        Добавляет аудиофайл в видео, сохраняя оригинальное качество видео и аудио.
        """
        duration, fps = get_video_duration(self.tmp_video_path, return_fps_too=True)
        audio_file = self.get_audio_full_path()

        logger.info(
            "Добавление аудио к видео:"
            "\n\tКодек видео: copy"
            f"\n\tКодек аудио: copy ({self.audio_format})"
            f"\n\tДлительность видео: {duration:.2f} сек"
            f"\n\tFPS видео: {fps}"
            f"\n\tПотоков: {self.threads}"
            f"\n\tРазрешение: {self.resolution}"
        )

        cmd = [
            "ffmpeg", "-y", "-i", self.tmp_video_path,
            "-i", audio_file,
            "-c:v", "copy",
            "-c:a", "copy",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest", "-progress", "-",
            "-threads", str(self.threads),
            "-nostats", "-loglevel", "error",
            self.out_video_path,
        ]
        try:
            run_ffmpeg_command_with_progress(
                cmd, duration, desc="Импортирование аудиоряда в видео", unit="сек"
            )
        except subprocess.CalledProcessError as e:
            logger.error(f"Ошибка при добавлении аудио: {str(e)}")
            raise

        # очистка временных файлов
        delete_file(audio_file)
        delete_file(self.tmp_video_path)
        logger.debug("Временные файлы удалены")

    def get_audio_full_path(self) -> str:
        """
        Возвращает полный путь к аудиофайлу, который будет извлечен из видеофайла.
        """
        filename = os.path.splitext(os.path.basename(self.in_video_path))[0]
        return os.path.join(self.audio_path, f"{filename}.{self.audio_format}")

    def delete_audio_if_exists(self, audio_path: str = None) -> None:
        """Удаляет аудиофайл, если он существует"""
        if audio_path is None:
            audio_path = self.get_audio_full_path()
        if os.path.exists(audio_path):
            delete_file(audio_path)
            logger.info(f"Аудиофайл удален: {audio_path}")
        else:
            logger.debug(f"Аудиофайл не найден: {audio_path}")

    def __check_audio_extracted(self, audio_file) -> None:
        """Проверяет успешность извлечения аудио"""
        if audio_file and os.path.exists(audio_file):
            logger.debug(f"Аудио успешно извлечено: {audio_file}")
            self.audio_path = audio_file
        else:
            logger.error("Аудио не найдено или не было извлечено")
            raise FileNotFoundError(
                "Аудиофайл не найден. Проверьте, было ли аудио успешно извлечено."
            )

    def __str__(self):
        return (
            f"AudioHandler(in_video_path={self.in_video_path}, "
            f"tmp_video_path={self.tmp_video_path}, "
            f"out_video_path={self.out_video_path}, "
            f"audio_path={self.audio_path}, "
            f"audio_format={self.audio_format}, "
            f"resolution={self.resolution})"
        )

    __repr__ = __str__
