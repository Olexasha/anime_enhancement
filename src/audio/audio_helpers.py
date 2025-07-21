import os
import subprocess

from src.utils.logger import logger


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
    logger.info(f"Запуск FFmpeg команды: {' '.join(cmd)}")
    logger.debug(f"Ожидаемая длительность: {duration:.1f} {unit}")

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            universal_newlines=True,
            bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        current_time = 0.0
        last_logged_progress = -1

        for line in process.stdout:
            if line.startswith("out_time_ms="):
                time_ms = int(line.strip().split("=")[1])
                time_sec = min(time_ms / 1_000_000, duration)
                if time_sec > current_time:
                    current_time = time_sec
                    progress_percent = (current_time / duration) * 100

                    # логируем каждые 5% прогресса или при значительном изменении
                    if (
                        int(progress_percent) > last_logged_progress + 4
                        or progress_percent >= 100
                    ):
                        logger.info(
                            f"{desc}: {progress_percent:.1f}% "
                            f"({current_time:.1f}/{duration:.1f} {unit})"
                        )
                        last_logged_progress = int(progress_percent)
        process.wait()
        if process.returncode != 0:
            logger.error(f"FFmpeg завершился с ошибкой (код: {process.returncode})")
            raise subprocess.CalledProcessError(process.returncode, cmd)
        logger.info(f"{desc} успешно завершена за {current_time:.1f} {unit}")
    except Exception as e:
        logger.error(f"Ошибка при выполнении FFmpeg: {str(e)}")
        raise
