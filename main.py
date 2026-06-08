from __future__ import annotations

import argparse
import asyncio
import glob
import json
import os
import re
import sys
from datetime import datetime
from math import ceil
from pathlib import Path
from typing import Any

from src.config.dependency_checker import check_environment, format_report, has_errors
from src.config.pipeline_config import PROJECT_ROOT, PipelineConfig

GUI_PROGRESS_PREFIX = "__GUI_PROGRESS__"


def configure_text_output() -> None:
    """Принудительно пишет stdout/stderr в UTF-8 для GUI/QProcess на Windows."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


configure_text_output()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Улучшение аниме-видео через ffmpeg, RealESRGAN, waifu2x и RIFE."
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Путь к JSON-профилю настроек.",
    )
    parser.add_argument(
        "--check-environment",
        action="store_true",
        help="Проверить окружение и завершить работу без обработки видео.",
    )
    parser.add_argument(
        "--print-effective-config",
        action="store_true",
        help="Вывести итоговую конфигурацию JSON и завершить работу без обработки видео.",
    )
    parser.add_argument(
        "--skip-environment-check",
        action="store_true",
        help="Не выполнять проверку ffmpeg и AI-утилит перед обработкой.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Проверить профиль, входной файл и окружение без запуска обработки.",
    )
    return parser.parse_args(argv)


def load_runtime_config(config_path: Path | None) -> PipelineConfig:
    config = (
        PipelineConfig.from_json(config_path)
        if config_path
        else PipelineConfig.from_env()
    )
    errors = config.validate(require_input_exists=False)
    if errors:
        joined = "\n".join(f"- {error}" for error in errors)
        raise ValueError(f"Некорректная конфигурация:\n{joined}")
    config.apply_to_environment()
    return config


def print_effective_config(config: PipelineConfig) -> None:
    print(json.dumps(config.to_json_payload(), indent=2, ensure_ascii=False))


def emit_gui_progress(value: int, status: str) -> None:
    if os.getenv("ANIME_ENHANCEMENT_GUI_PROGRESS") != "1":
        return
    safe_value = max(0, min(100, int(value)))
    safe_status = status.replace("\n", " ").replace("|", "/")
    print(f"{GUI_PROGRESS_PREFIX}|{safe_value}|{safe_status}", flush=True)


def print_header(title: str) -> None:
    from src.utils.logger import logger

    logger.info("=" * 50)
    logger.info(title.upper().center(50))


def print_bottom(title: str) -> None:
    from src.utils.logger import logger

    logger.info(title.upper().center(50))
    logger.info(f"{'=' * 50}\n")


async def clean_up(audio: Any) -> None:
    from src.config import settings
    from src.files.batch_utils import BatchType, delete_all_batches
    from src.files.file_actions import delete_file
    from src.utils.logger import logger

    if settings.KEEP_TEMP_FILES:
        logger.info("Очистка временных файлов пропущена: KEEP_TEMP_FILES=true")
        return

    logger.debug("Начало очистки временных файлов")
    delete_tasks = [
        delete_all_batches(BatchType.DEFAULT),
        delete_all_batches(BatchType.DENOISE),
        delete_all_batches(BatchType.UPSCALE),
        delete_all_batches(BatchType.INTERPOLATE),
        audio.delete_audio_if_exists(),
    ]
    delete_tasks.extend(
        delete_file(f)
        for f in glob.glob(os.path.join(settings.BATCH_VIDEO_PATH, "*.mp4"))
    )
    delete_tasks.extend(
        delete_file(f)
        for f in glob.glob(os.path.join(settings.TMP_VIDEO_PATH, "*.mp4"))
    )
    if delete_tasks:
        await asyncio.gather(*delete_tasks)
    logger.debug("Временные файлы успешно удалены")


def calculate_batches() -> int:
    from src.config import settings
    from src.utils.logger import logger

    if settings.END_BATCH_TO_IMPROVE == 0:
        batch_name_pattern = re.compile(r"batch_(\d+)")
        batch_count = len(
            [
                batch
                for batch in os.listdir(settings.INPUT_BATCHES_DIR)
                if batch_name_pattern.match(batch)
            ]
        )
        logger.debug(f"Автоопределение количества батчей: {batch_count}")
        return batch_count

    logger.debug(
        f"Использовано фиксированное количество батчей: {settings.END_BATCH_TO_IMPROVE}"
    )
    return settings.END_BATCH_TO_IMPROVE


async def process_batches(
    threads: int,
    ai_threads: str,
    video: Any,
    ai_waifu2x_path: str,
    ai_realesrgan_path: str,
    ai_rife_path: str,
    start_batch: int,
    end_batch_to_improve: int,
) -> None:
    from src.config import settings
    from src.files.batch_utils import (
        delete_default_batches,
        delete_denoise_batches,
        delete_upscale_batches,
    )
    from src.frames.improve import ProcessingType, improve_batches
    from src.utils.logger import logger

    end_batch = 0
    first_batch = start_batch
    total_batches = max(1, end_batch_to_improve - first_batch + 1)
    while end_batch != end_batch_to_improve:
        end_batch = min(start_batch + threads - 1, end_batch_to_improve)
        logger.info(f"Обработка батчей с {start_batch} по {end_batch}")

        if settings.ENABLE_DENOISE:
            await improve_batches(
                ProcessingType.DENOISE,
                threads,
                ai_threads,
                ai_waifu2x_path,
                start_batch,
                end_batch,
            )
            if not settings.KEEP_TEMP_FILES:
                await delete_default_batches(start_batch, end_batch)
            logger.success(
                f"Батчи {start_batch}-{end_batch} успешно обработаны денойзом"
            )
        else:
            logger.info("Денойз отключен: исходные PNG-кадры идут напрямую в апскейл")

        await improve_batches(
            ProcessingType.UPSCALE,
            threads,
            ai_threads,
            ai_realesrgan_path,
            start_batch,
            end_batch,
        )
        if not settings.KEEP_TEMP_FILES:
            if settings.ENABLE_DENOISE:
                await delete_denoise_batches(start_batch, end_batch)
            else:
                await delete_default_batches(start_batch, end_batch)
        logger.success(f"Батчи {start_batch}-{end_batch} успешно апскейлены")

        if settings.ENABLE_INTERPOLATION:
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
                if not settings.KEEP_TEMP_FILES:
                    await delete_upscale_batches(batches[0], batches[-1])
            logger.success(f"Батчи {start_batch}-{end_batch} успешно интерполированы")
        else:
            logger.info(
                "Интерполяция отключена: видео собирается из апскейленных кадров"
            )

        batches_to_perform = [f"batch_{i}" for i in range(start_batch, end_batch + 1)]
        video.build_short_video(batches_to_perform)
        completed_batches = max(0, end_batch - first_batch + 1)
        batch_progress = completed_batches / total_batches
        emit_gui_progress(
            30 + round(batch_progress * 55),
            f"ИИ-обработка батчей: {completed_batches}/{total_batches}",
        )
        start_batch += threads


async def run_pipeline() -> None:
    from src.audio.audio_handling import AudioHandler
    from src.config import settings
    from src.config.comp_params import ComputerParams
    from src.frames.frames_helpers import extract_frames_to_batches, get_fps_accurate
    from src.utils.logger import logger
    from src.video.video_handling import VideoHandler

    start_time = datetime.now()
    emit_gui_progress(0, "Запуск улучшения видео")
    print_header("запуск улучшения видео")

    try:
        emit_gui_progress(3, "Проверка системы и путей к AI-утилитам")
        my_computer = ComputerParams()
        ai_realesrgan_path = my_computer.ai_realesrgan_path
        ai_waifu2x_path = my_computer.ai_waifu2x_path
        ai_rife_path = my_computer.ai_rife_path
        ai_threads, process_threads = my_computer.get_optimal_threads()

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

        print_header("извлекаем кадры и готовим аудио")
        emit_gui_progress(8, "Подготовка кадров и аудио")
        audio = AudioHandler(threads=my_computer.safe_cpu_threads // 2)
        await clean_up(audio)

        asyncio.create_task(audio.extract_audio())
        extract_frames_to_batches(my_computer.safe_cpu_threads // 2)
        fps = await asyncio.to_thread(get_fps_accurate, settings.ORIGINAL_VIDEO)
        video = VideoHandler(fps=fps)
        print_bottom("кадры и аудио подготовлены")
        emit_gui_progress(25, "Кадры и аудио подготовлены")

        print_header("генерируем улучшенные короткие видео")
        end_batch_to_improve = calculate_batches()
        logger.info(f"Всего батчей для обработки: {end_batch_to_improve}")
        emit_gui_progress(30, f"Начало ИИ-обработки батчей: {end_batch_to_improve}")
        await process_batches(
            process_threads,
            ai_threads,
            video,
            ai_waifu2x_path,
            ai_realesrgan_path,
            ai_rife_path,
            settings.START_BATCH_TO_IMPROVE,
            end_batch_to_improve,
        )
        print_bottom("улучшенные короткие видео сгенерированы")
        emit_gui_progress(85, "Короткие улучшенные видео сгенерированы")

        print_header("начало финальной сборки видео")
        emit_gui_progress(90, "Финальная сборка видео")
        total_short_videos = ceil(end_batch_to_improve / process_threads)
        final_merge = await video.build_final_video(total_short_videos)
        logger.success(f"Общее видео собрано: {final_merge}")

        logger.info("Добавление аудиодорожки к финальному видео")
        emit_gui_progress(95, "Добавление аудиодорожки")
        audio.tmp_video_path = final_merge
        await audio.insert_audio()
        logger.success(f"Аудио добавлено к {settings.FINAL_VIDEO}")
        print_bottom("финальная сборка завершена")

        logger.success(f"Итоговое видео сохранено: {settings.FINAL_VIDEO}")
        emit_gui_progress(100, "Готово")
        execution_time = datetime.now() - start_time
        logger.info(f"Общее время выполнения: {execution_time}")
        print_bottom("улучшение видео завершено")
    except Exception as error:
        logger.critical(f"Критическая ошибка: {str(error)}")
        raise


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = load_runtime_config(args.config)
        if args.print_effective_config:
            print_effective_config(config)
            return 0

        if args.check_environment:
            checks = check_environment(config, PROJECT_ROOT)
            print(format_report(checks))
            return 1 if has_errors(checks) else 0

        input_errors = config.validate(require_input_exists=True)
        if input_errors:
            raise ValueError(
                "Некорректная конфигурация:\n"
                + "\n".join(f"- {error}" for error in input_errors)
            )

        if not args.skip_environment_check:
            checks = check_environment(config, PROJECT_ROOT)
            if has_errors(checks):
                raise RuntimeError(
                    "Проверка окружения не пройдена:\n" + format_report(checks)
                )

        if args.dry_run:
            print(
                "Профиль, входной файл и окружение проверены. Обработка не запускалась."
            )
            return 0

        asyncio.run(run_pipeline())
        return 0
    except Exception as error:
        print(f"Критическая ошибка: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
