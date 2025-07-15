import os
import subprocess
from typing import Optional

from colorama import Fore, Style
from moviepy import VideoFileClip
from tqdm import tqdm

from src.config.settings import ALLOWED_THREADS, AUDIO_PATH, ORIGINAL_VIDEO, RESOLUTION
from src.utils.file_utils import delete_file
from src.video.video_helpers import get_video_duration


def get_audio_full_path(video_path: str, audio_dir: str, extension: str = "aac") -> str:
    """
    Возвращает полный путь к аудиофайлу, который будет извлечен из видеофайла.

    :param video_path: Путь к исходному видеофайлу.
    :param audio_dir: Директория, куда будет сохранен аудиофайл.
    :param extension: Расширение для аудиофайла. По умолчанию 'aac'.
    :return: Полный путь к аудиофайлу с указанным расширением.
    """
    filename = os.path.splitext(os.path.basename(video_path))[0]
    return os.path.join(audio_dir, f"{filename}.{extension}")


def delete_audio_if_exists(audio_path: str) -> None:
    """
    Удаляет аудиофайл, если он существует.

    :param audio_path: Путь к аудиофайлу.
    """
    if os.path.exists(audio_path):
        delete_file(audio_path)
        print(f"🗑️ Аудиофайл {audio_path} успешно удален.")
    else:
        print(f"⚠️ Аудиофайл {audio_path} не найден, удаление не требуется.")


def extract_audio(
    video_path: str = ORIGINAL_VIDEO,
    audio_path: str = AUDIO_PATH,
    extension: str = "mp3",
) -> Optional[str]:
    """
    Извлекает аудио из видеофайла и сохраняет его как отдельный аудиофайл.

    :param video_path: Путь к исходному видеофайлу.
    :param audio_path: Директория, куда будет сохранен аудиофайл.
    :param extension: Расширение для аудиофайла. По умолчанию 'mp3'.
    :return: Путь к созданному аудиофайлу или None, если аудиопоток не найден.
    """
    audio_file = get_audio_full_path(video_path, audio_path, extension)
    delete_audio_if_exists(audio_file)
    print(f"\n🎵 Начинаем извлечение аудио из видео...")
    print(f"📁 Видео: {video_path}")
    print(f"🎧 Выходной файл: {audio_file}")
    with VideoFileClip(video_path) as clip:
        if not clip.audio:
            print("🚨 Ошибка: аудио не найдено в видеофайле.")
            return None

        print(f"🔊 Параметры извлечения аудио:")
        print(f"\t🔉 Кодек: {'libmp3lame' if extension == 'mp3' else extension}")
        print(f"\t🎚️ Битрейт: 192k")
        print(f"\t🎛️ Частота дискретизации: 44100 Hz")
        print(f"\t🎧 Каналы: 2 (стерео)")

        clip.audio.write_audiofile(
            audio_file,
            codec="libmp3lame" if extension == "mp3" else extension,
            bitrate="192k",
            ffmpeg_params=["-vn", "-ar", "44100", "-ac", "2"],
        )
        return audio_file


def insert_audio(
    audio_path: str,
    video_path: str,
    output_path: str,
    audio_format: str = "mp3",
    resolution: str = RESOLUTION,
) -> None:
    """
    Добавляет аудиофайл в видео, сохраняя оригинальное качество видео и аудио, с учетом разрешения видео.

    :param audio_path: Путь к аудиофайлу.
    :param audio_format: Расширение аудиофайла. По умолчанию 'mp3'.
    :param video_path: Путь к видеофайлу, в который будет добавлено аудио.
    :param output_path: Путь к итоговому файлу, куда будет сохранено видео с аудиодорожкой.
    :param resolution: Разрешение видео ('4K' или '8K'), чтобы задать соответствующий битрейт. По умолчанию '4K'.
    :return: None
    """
    print(f"\n🎬 Начинаем добавление аудио к видео...")
    print(f"📹 Видео: {video_path}")
    print(f"🎧 Аудио: {audio_path}")
    print(f"💾 Выходной файл: {output_path}")

    duration, fps = get_video_duration(video_path, return_fps_too=True)

    print(f"\n⚙️ Параметры обработки:")
    print(f"\t🎞️ Кодек видео: исходный (копирование)")
    print(f"\t🔊 Кодек аудио: исходный ({audio_format})")
    print(f"\t⏱ Длительность видео: {duration:.2f} сек")
    print(f"\t🎥 FPS видео: {fps}")
    print(f"\t🧵 Потоков: {ALLOWED_THREADS}")
    print(f"\t🖥️ Разрешение: {resolution}")

    cmd = [
        "ffmpeg",
        "-y",
        "-i", video_path,
        "-i", audio_path,
        "-c:v", "copy",
        "-c:a", "copy",
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-shortest",
        "-progress", "-",
        "-threads", str(ALLOWED_THREADS),
        "-nostats",
        "-loglevel", "error",
        output_path,
    ]

    try:
        with tqdm(
            total=duration,
            desc=f"{Fore.GREEN}Добавление аудио к видео{Style.RESET_ALL}",
            unit="сек",
            colour="green",
            bar_format="{l_bar}{bar}| {n:.1f}/{total:.1f} сек [{elapsed}<{remaining}]",
        ) as pbar:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            current_time = 0
            for line in process.stdout:
                if line.startswith("out_time_ms="):
                    time_ms = int(line.split("=")[1].strip())
                    time_sec = time_ms / 1_000_000  # мкс в секунды
                    if time_sec > current_time:
                        pbar.update(time_sec - current_time)
                        current_time = time_sec
            if process.wait() != 0:
                raise subprocess.CalledProcessError(process.returncode, cmd)
        print(
            f"✅ Аудио успешно добавлено в видео. Итоговое видео сохранено в {output_path}"
        )
    except subprocess.CalledProcessError as e:
        print(f"🚨 Ошибка при добавлении аудио: {e}")
        raise

    delete_file(audio_path)
    delete_file(video_path)
