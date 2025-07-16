import os
import subprocess

from colorama import Fore, Style
from tqdm import tqdm

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


def delete_audio_if_exists(audio_path: str) -> None:
    """
    Удаляет аудиофайл, если он существует.

    :param audio_path: Путь к аудиофайлу.
    """
    if os.path.exists(audio_path):
        delete_file(audio_path)
        print(f"🗑️ Аудиофайл {audio_path} успешно удален.")
    else:
        print(f"Аудиофайл {audio_path} не найден, удаление не требуется.")


def run_ffmpeg_command_with_progress(
    cmd: list, duration: float, desc: str = "Обработка", unit: str = "сек"
) -> None:
    """
    Запускает команду ffmpeg с прогресс-баром, отображающим время обработки.

    :param cmd: Команда для запуска ffmpeg в виде списка.
    :param duration: Общее время обработки в секундах (видео в сек).
    :param desc: Описание задачи для прогресс-бара.
    :param unit: Единица измерения для прогресс-бара (по умолчанию "сек").
    """
    with tqdm(
        total=round(duration, 1),
        desc=f"{Fore.GREEN}{desc}{Style.RESET_ALL}",
        unit=unit,
        bar_format="{l_bar}{bar}| {n:.1f}/{total:.1f} сек [{elapsed}<{remaining}]",
        colour="green",
        ncols=150,
        mininterval=0.5,
    ) as pbar:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            universal_newlines=True,
            bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        current_time = 0
        for line in process.stdout:
            if line.startswith("out_time_ms="):
                time_ms = int(line.strip().split("=")[1])
                time_sec = min(time_ms / 1_000_000, duration)
                if time_sec > current_time:
                    pbar.update(time_sec - current_time)
                    current_time = time_sec
        process.wait()
        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, cmd)
