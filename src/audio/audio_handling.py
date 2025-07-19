import asyncio
import os
import subprocess
from concurrent.futures import ProcessPoolExecutor
from typing import Optional

from src.audio.audio_helpers import run_ffmpeg_command_with_progress
from src.config.settings import (
    ALLOWED_CPU_THREADS,
    AUDIO_PATH,
    FINAL_VIDEO,
    ORIGINAL_VIDEO,
    RESOLUTION,
    TMP_VIDEO_PATH,
)
from src.files.file_actions import delete_file
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
        input_video_path: str = ORIGINAL_VIDEO,
        merged_video_path: str = TMP_VIDEO_PATH,
        output_video_path: str = FINAL_VIDEO,
        audio_path: str = AUDIO_PATH,
        audio_format: str = "mp3",
        resolution: str = RESOLUTION,
    ):
        self.in_video_path = input_video_path
        self.tmp_video_path = merged_video_path
        self.out_video_path = output_video_path
        self.audio_path = audio_path
        self.audio_format = audio_format
        self.resolution = resolution
        self.codec = "libmp3lame" if self.audio_format == "mp3" else self.audio_format

        print(f"🔊 Параметры аудио:")
        print(f"\tКодек: {self.codec}")
        print(f"\tБитрейт: {self.BITRATE}")
        print(f"\tЧастота дискретизации: {self.SAMPLE_FREQ} Hz")
        print(f"\tКаналы: {self.CANALS} (стерео)")

    def extract_audio_sync(self) -> Optional[str]:
        """
        Извлекает аудио из видеофайла и сохраняет его как отдельный аудиофайл.
        """
        audio_file = self.get_audio_full_path()
        print(f"\n🎵 Извлечение аудио из: {self.in_video_path}")
        print(f"Сохранение в: {audio_file}")

        ffmpeg_args = [
            "-y", "-i", self.in_video_path,
            "-vn", "-acodec", self.codec,
            "-ar", self.SAMPLE_FREQ, "-ac", self.CANALS,
            "-b:a", self.BITRATE, "-threads", str(ALLOWED_CPU_THREADS),
            "-loglevel", "error", audio_file,
        ]

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

    async def extract_audio(self) -> Optional[str]:
        loop = asyncio.get_running_loop()
        with ProcessPoolExecutor() as pool:
            return await loop.run_in_executor(pool, self.extract_audio_sync)

    def insert_audio(self) -> None:
        """
        Добавляет аудиофайл в видео, сохраняя оригинальное качество видео и аудио, с учетом разрешения видео.
        """
        duration, fps = get_video_duration(self.tmp_video_path, return_fps_too=True)
        audio_file = self.get_audio_full_path()
        print(f"\n⚙️ Параметры обработки:")
        print(f"\tКодек видео: исходный (копирование)")
        print(f"\tКодек аудио: исходный ({self.audio_format})")
        print(f"\tДлительность видео: {duration:.2f} сек")
        print(f"\tFPS видео: {fps}")
        print(f"\tПотоков: {ALLOWED_CPU_THREADS}")
        print(f"\tРазрешение: {self.resolution}")

        cmd = [
            "ffmpeg", "-y", "-i", self.tmp_video_path,
            "-i", audio_file,
            "-c:v", "copy",
            "-c:a", "copy",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest", "-progress", "-",
            "-threads", str(ALLOWED_CPU_THREADS),
            "-nostats", "-loglevel", "error",
            self.out_video_path,
        ]
        try:
            run_ffmpeg_command_with_progress(
                cmd, duration, desc="Добавление аудио к видео", unit="сек"
            )
        except subprocess.CalledProcessError as e:
            print(f"🚨 Ошибка при добавлении аудио: {e}")
            raise
        delete_file(audio_file)
        delete_file(self.tmp_video_path)

    def get_audio_full_path(self) -> str:
        """
        Возвращает полный путь к аудиофайлу, который будет извлечен из видеофайла.
        """
        filename = os.path.splitext(os.path.basename(self.in_video_path))[0]
        return os.path.join(self.audio_path, f"{filename}.{self.audio_format}")

    def delete_audio_if_exists(self, audio_path: str = None) -> None:
        """
        Удаляет аудиофайл, если он существует.

        :param audio_path: Путь к аудиофайлу.
        """
        if audio_path is None:
            audio_path = self.get_audio_full_path()
        if os.path.exists(audio_path):
            delete_file(audio_path)
            print(f"\n🗑️ Аудиофайл {audio_path} успешно удален.\n")
        else:
            print(f"\nАудиофайл {audio_path} не найден, удаление не требуется.\n")

    def __check_audio_extracted(self, audio_file) -> None:
        """
        Проверяет, было ли аудио успешно извлечено из видеофайла.
        Возвращает True, если аудио существует, иначе False.
        """
        if audio_file and os.path.exists(audio_file):
            print(f"\n\n✅ Аудио успешно извлечено: {audio_file}\n")
            self.audio_path = audio_file
        else:
            print("\n\n⚠️ Аудио не найдено или не было извлечено.\n")
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

    def __repr__(self):
        return self.__str__()
