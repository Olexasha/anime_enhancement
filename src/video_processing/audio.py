import os
from typing import Optional

from moviepy import AudioFileClip, CompositeAudioClip, VideoFileClip

from src.config.settings import ALLOWED_THREADS, AUDIO_PATH, ORIGINAL_VIDEO, RESOLUTION
from src.utils.file_utils import delete_file


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
    with VideoFileClip(video_path) as clip:
        if clip.audio:
            print(
                f"Планируется временное извлечение аудиодорожки из видео со следующими параметрами:"
                f"\n\tкодек - `{'libmp3lame' if extension == 'mp3' else extension}`"
                f"\n\tбитрейт - `192k`"
                f"\n\tчастота дискретизации - `44100`"
                f"\n\tколичество каналов - `2`"
            )
            clip.audio.write_audiofile(
                audio_file,
                codec="libmp3lame" if extension == "mp3" else extension,
                bitrate="192k",
                ffmpeg_params=["-vn", "-ar", "44100", "-ac", "2"],
            )
            return audio_file
        else:
            print("Аудио не найдено в видеофайле.")
            return None


def insert_audio(
    audio_path: str,
    fps: float,
    video_path: str,
    output_path: str,
    audio_format: str = "mp3",
    resolution: str = RESOLUTION,
) -> None:
    """
    Добавляет аудиофайл в видео, сохраняя оригинальное качество видео и аудио, с учетом разрешения видео.

    :param audio_path: Путь к аудиофайлу.
    :param fps: Количество кадров в секунду.
    :param audio_format: Расширение аудиофайла. По умолчанию 'mp3'.
    :param video_path: Путь к видеофайлу, в который будет добавлено аудио.
    :param output_path: Путь к итоговому файлу, куда будет сохранено видео с аудиодорожкой.
    :param resolution: Разрешение видео ('4K' или '8K'), чтобы задать соответствующий битрейт. По умолчанию '4K'.
    :return: None
    """
    with VideoFileClip(video_path) as video, AudioFileClip(audio_path) as audio:
        audio_set = CompositeAudioClip([audio])
        video_with_audio = video.with_audio(audio_set)
        print(
            f"Планируется добавление аудиодорожки в видео со следующими параметрами:"
            f"\n\tкодек - `libx265`"
            f"\n\tформат аудио - `{audio_format}`"
            f"\n\tчастота кадров - `{fps}`"
            f"\n\tпресет - `slow`"
            f"\n\tколичество потоков - `{ALLOWED_THREADS}`"
            f"\n\tбитрейт - `{'20000k' if resolution == '4K' else '40000k'}`"
            f"\n\tразрешение - `{resolution}`"
        )
        video_with_audio.write_videofile(
            output_path,
            codec="libx265",
            audio_codec=audio_format,
            fps=fps,
            preset="slow",
            threads=ALLOWED_THREADS,
            bitrate="20000k" if resolution == "4K" else "40000k",
        )
    delete_file(audio_path)
    delete_file(video_path)
    print(f"Аудиодорожка добавлена в видеофайл {output_path}.")
