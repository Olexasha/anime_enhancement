import asyncio
import os
import subprocess
from typing import Optional

from src.audio.audio_helpers import (
    delete_audio_if_exists,
    get_audio_full_path,
    run_ffmpeg_command_with_progress,
)
from src.config.settings import (
    ALLOWED_THREADS,
    AUDIO_PATH,
    FINAL_VIDEO,
    ORIGINAL_VIDEO,
    RESOLUTION,
    TMP_VIDEO,
)
from src.utils.file_utils import delete_file
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
        merged_video_path: str = TMP_VIDEO,
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

    def check_audio_extracted(self, audio_file) -> None:
        """
        Проверяет, было ли аудио успешно извлечено из видеофайла.
        Возвращает True, если аудио существует, иначе False.
        """
        if audio_file and os.path.exists(audio_file):
            print(f"✅ Аудио успешно извлечено: {audio_file}\n")
            self.audio_path = audio_file
        else:
            print("⚠️ Аудио не найдено или не было извлечено.")
            raise FileNotFoundError(
                "Аудиофайл не найден. Проверьте, было ли аудио успешно извлечено."
            )

    async def extract_audio(self) -> Optional[str]:
        """
        Извлекает аудио из видеофайла и сохраняет его как отдельный аудиофайл.
        """
        audio_file = get_audio_full_path(
            self.in_video_path, self.audio_path, self.audio_format
        )
        delete_audio_if_exists(audio_file)
        print(f"\n🎵 Извлечение аудио из: {self.in_video_path}")
        print(f"Сохранение в: {audio_file}")
        duration = get_video_duration(self.in_video_path)

        def __sync_extract():
            cmd = [
                "ffmpeg", "-y", "-i", self.in_video_path,
                "-vn", "-acodec", self.codec,
                "-ar", self.SAMPLE_FREQ,
                "-ac", self.CANALS,
                "-b:a", self.BITRATE,
                "-progress", "-",
                "-threads", str(ALLOWED_THREADS),
                "-loglevel", "error",
                audio_file,
            ]
            try:
                run_ffmpeg_command_with_progress(
                    cmd, duration, desc="Извлечение аудио", unit="сек"
                )
            except subprocess.CalledProcessError as e:
                print(f"🚨 Ошибка при извлечении аудио: {e}")
                return None
            self.check_audio_extracted(audio_file)

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, __sync_extract)

    async def insert_audio(self) -> None:
        """
        Добавляет аудиофайл в видео, сохраняя оригинальное качество видео и аудио, с учетом разрешения видео.
        """
        print(f"\n🎬 Начинаем добавление аудио к видео...")
        print(f"Видео: {self.tmp_video_path}")
        print(f"Аудио: {self.audio_path}")
        print(f"Выходной файл: {self.out_video_path}")

        def __sync_insert():
            duration, fps = get_video_duration(self.tmp_video_path, return_fps_too=True)

            print(f"\n⚙️ Параметры обработки:")
            print(f"\tКодек видео: исходный (копирование)")
            print(f"\tКодек аудио: исходный ({self.audio_format})")
            print(f"\tДлительность видео: {duration:.2f} сек")
            print(f"\tFPS видео: {fps}")
            print(f"\tПотоков: {ALLOWED_THREADS}")
            print(f"\tРазрешение: {self.resolution}")

            cmd = [
                "ffmpeg", "-y", "-i", self.tmp_video_path,
                "-i", self.audio_path,
                "-c:v", "copy",
                "-c:a", "copy",
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-shortest", "-progress", "-",
                "-threads", str(ALLOWED_THREADS),
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
            delete_file(self.audio_path)
            delete_file(self.tmp_video_path)

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, __sync_insert)

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
