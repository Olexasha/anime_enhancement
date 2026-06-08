import asyncio
import glob
import os
import re
from datetime import datetime
from math import ceil

from src.audio.audio_handling import AudioHandler
from src.config.comp_params import ComputerParams
from src.config.settings import (
    BATCH_VIDEO_PATH,
    ENABLE_DENOISE,
    ENABLE_INTERPOLATION,
    END_BATCH_TO_IMPROVE,
    FINAL_VIDEO,
    INPUT_BATCHES_DIR,
    ORIGINAL_VIDEO,
    START_BATCH_TO_IMPROVE,
    TMP_VIDEO_PATH,
)
from src.files.batch_utils import (
    BatchType,
    delete_all_batches,
    delete_default_batches,
    delete_denoise_batches,
    delete_upscale_batches,
)
from src.files.file_actions import delete_file
from src.frames.frames_helpers import extract_frames_to_batches, get_fps_accurate
from src.frames.improve import ProcessingType, improve_batches
from src.utils.logger import logger
from src.video.video_handling import VideoHandler


def print_header(title: str) -> None:
    """Логирует префикс программы."""
    logger.info(f"{'=' * 50}")
    logger.info(f"🎯 {title.upper()}".center(50))


def print_bottom(title: str) -> None:
    """Логирует постфикс программы."""
    logger.info(f"✅ {title.upper()}".center(50))
    logger.info(f"{'=' * 50}\n")


async def clean_up(audio: AudioHandler) -> None:
    """Удаляет временные файлы."""
    logger.debug("Начало очистки временных файлов")
    delete_tasks = [
        delete_all_batches(BatchType.DEFAULT),  # Удаляем все default батчи
        delete_all_batches(BatchType.DENOISE),  # Удаляем все denoise батчи
        delete_all_batches(BatchType.UPSCALE),  # Удаляем все upscale батчи
        delete_all_batches(BatchType.INTERPOLATE),  # Удаляем все interpolate батчи
        audio.delete_audio_if_exists(),
    ]
    delete_tasks.extend(
        delete_file(f) for f in glob.glob(os.path.join(BATCH_VIDEO_PATH, "*.mp4"))
    )
    delete_tasks.extend(
        delete_file(f) for f in glob.glob(os.path.join(TMP_VIDEO_PATH, "*.mp4"))
    )
    if delete_tasks:
        await asyncio.gather(*delete_tasks)
    logger.debug("Временные файлы успешно удалены")


def calculate_batches() -> int:
    """Вычисляет количество батчей для обработки."""
    if END_BATCH_TO_IMPROVE == 0:
        batch_name_pattern = re.compile(r"batch_(\d+)")
        batch_count = len(
            [
                batch
                for batch in os.listdir(INPUT_BATCHES_DIR)
                if batch_name_pattern.match(batch)
            ]
        )
        logger.debug(f"Автоопределение количества батчей: {batch_count}")
        return batch_count

    logger.debug(
        f"Использовано фиксированное количество батчей: {END_BATCH_TO_IMPROVE}"
    )
    return END_BATCH_TO_IMPROVE


async def process_batches(
    threads: int,
    ai_threads: str,
    video: VideoHandler,
    ai_waifu2x_path: str,
    ai_realesrgan_path: str,
    ai_rife_path: str,
    start_batch: int,
    end_batch_to_improve: int,
) -> None:
    """Обрабатывает батчи с кадрами."""
    end_batch = 0
    while end_batch != end_batch_to_improve:
        end_batch = min(start_batch + threads - 1, end_batch_to_improve)
        logger.info(f"Обработка батчей с {start_batch} по {end_batch}")

        if ENABLE_DENOISE:
            # --- Денойз ---
            await improve_batches(
                ProcessingType.DENOISE,
                threads,
                ai_threads,
                ai_waifu2x_path,
                start_batch,
                end_batch,
            )
            await delete_default_batches(start_batch, end_batch)
            logger.success(f"Батчи {start_batch}-{end_batch} успешно денойзены")
        else:
            logger.info("Денойз отключен: исходные PNG-кадры идут напрямую в апскейл")

        # --- Апскейл ---
        await improve_batches(
            ProcessingType.UPSCALE,
            threads,
            ai_threads,
            ai_realesrgan_path,
            start_batch,
            end_batch,
        )
        if ENABLE_DENOISE:
            await delete_denoise_batches(start_batch, end_batch)
        else:
            await delete_default_batches(start_batch, end_batch)
        logger.success(f"Батчи {start_batch}-{end_batch} успешно апскейлены")

        if ENABLE_INTERPOLATION:
            # --- Интерполяция ---
            interpolate_threads = max(1, threads // 3)
            batch_nums = list(range(start_batch, end_batch + 1))

            for i in range(0, len(batch_nums), interpolate_threads):
                batches = batch_nums[i : i + interpolate_threads]
                logger.info(
                    f"Интерполяция батчей {batches} ({interpolate_threads} процессов)"
                )

                await improve_batches(
                    ProcessingType.INTERPOLATE,
                    interpolate_threads,
                    ai_threads,
                    ai_rife_path,
                    batches[0],
                    batches[-1],
                )
                await delete_upscale_batches(batches[0], batches[-1])
            logger.success(f"Батчи {start_batch}-{end_batch} успешно интерполированы")
        else:
            logger.info(
                "Интерполяция отключена: видео собирается из апскейленных кадров"
            )

        batches_to_perform = [f"batch_{i}" for i in range(start_batch, end_batch + 1)]
        video.build_short_video(batches_to_perform)
        start_batch += threads


async def main():
    """Основной процесс обработки видео."""
    start_time = datetime.now()
    print_header("запуск улучшения видео")

    try:
        my_computer = ComputerParams()
        ai_realesrgan_path = my_computer.ai_realesrgan_path
        ai_waifu2x_path = my_computer.ai_waifu2x_path
        ai_rife_path = my_computer.ai_rife_path
        ai_threads, process_threads = my_computer.get_optimal_threads()

        # логирование параметров системы
        logger.info(
            "Параметры системы:"
            f"\n\tОС: {my_computer.cpu_name}"
            f"\n\tCPU потоки: {my_computer.cpu_threads}"
            f"\n\tБезопасные потоки: {my_computer.safe_cpu_threads}"
            f"\n\tСкорость SSD: ~{my_computer.ssd_speed} MB/s"
            f"\n\tRAM: ~{my_computer.ram_total} GB"
            f"\n\tПараметры нейронок: -j {ai_threads}"
            f"\n\tПуть к нейронке денойза: {ai_waifu2x_path}"
            f"\n\tПуть к нейронке апскейла: {ai_realesrgan_path}"
            f"\n\tПуть к нейронке интерполяции: {ai_rife_path}"
        )

        print_header("извлекаем 'сырьё' из видео...")
        audio = AudioHandler(threads=my_computer.safe_cpu_threads // 2)
        await clean_up(audio)

        # запускаем извлечение аудио из видео в фоне
        asyncio.create_task(audio.extract_audio())
        extract_frames_to_batches(my_computer.safe_cpu_threads // 2)
        fps = await asyncio.to_thread(get_fps_accurate, ORIGINAL_VIDEO)
        video = VideoHandler(fps=fps)
        print_bottom("`сырьё` из видео извлечено")

        # определяем диапазон батчей для обработки
        print_header("генерируем улучшенные короткие видео...")
        end_batch_to_improve = calculate_batches()
        logger.info(f"Всего батчей для обработки: {end_batch_to_improve}")
        await process_batches(
            process_threads,
            ai_threads,
            video,
            ai_waifu2x_path,
            ai_realesrgan_path,
            ai_rife_path,
            START_BATCH_TO_IMPROVE,
            end_batch_to_improve,
        )
        print_bottom("улучшенные короткие видео сгенерированы")

        print_header("начало финальной сборки видео...")
        total_short_videos = ceil(end_batch_to_improve / process_threads)
        final_merge = await video.build_final_video(total_short_videos)
        logger.success(f"Общее видео собрано: {final_merge}")

        logger.info("Добавление аудиодорожки к финальному видео")
        audio.tmp_video_path = final_merge
        await audio.insert_audio()
        logger.success(f"Аудио добавлено к {FINAL_VIDEO}")
        print_bottom("финальная сборка завершена")

        logger.success(f"Итоговое видео сохранено: {FINAL_VIDEO}")
        execution_time = datetime.now() - start_time
        logger.info(f"Общее время выполнения: {execution_time}")
        print_bottom("улучшение видео завершено")
    except Exception as error:
        logger.critical(f"Критическая ошибка: {str(error)}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
