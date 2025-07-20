import asyncio
import os
import re
from datetime import datetime

from src.audio.audio_handling import AudioHandler
from src.config.comp_params import ComputerParams
from src.config.settings import (
    END_BATCH_TO_UPSCALE,
    FINAL_VIDEO,
    INPUT_BATCHES_DIR,
    ORIGINAL_VIDEO,
    START_BATCH_TO_UPSCALE,
)
from src.frames.frames_helpers import extract_frames_to_batches, get_fps_accurate
from src.frames.upscale import delete_frames, upscale_batches
from src.video.video_handling import VideoHandler


def print_header(title: str) -> None:
    """Выводит заголовок программы."""
    print(f"\n{'=' * 50}")
    print(f"🎯 {title.upper()}".center(50))
    print(f"{'=' * 50}")


async def clean_up(audio: AudioHandler) -> None:
    """Удаляет временные файлы."""
    await asyncio.gather(
        asyncio.to_thread(audio.delete_audio_if_exists),
        asyncio.to_thread(delete_frames, del_upscaled=False),
        asyncio.to_thread(delete_frames, del_upscaled=True),
    )


def calculate_batches() -> int:
    """Вычисляет количество батчей для обработки."""
    if END_BATCH_TO_UPSCALE == 0:
        batch_name_pattern = re.compile(r"batch_(\d+)")
        return len(
            [
                batch
                for batch in os.listdir(INPUT_BATCHES_DIR)
                if batch_name_pattern.match(batch)
            ]
        )
    return END_BATCH_TO_UPSCALE


async def process_batches(
    threads: int,
    ai_threads: str,
    video: VideoHandler,
    ai_realesrgan_path: str,
    start_batch: int,
    end_batch_to_upscale: int,
) -> None:
    """Обрабатывает батчи с кадрами."""
    end_batch = 0
    while end_batch != end_batch_to_upscale:
        end_batch = min(start_batch + threads - 1, end_batch_to_upscale)
        print(f"\n🔄 Обрабатываем батчи с {start_batch} по {end_batch}...")

        await upscale_batches(
            threads, ai_threads, ai_realesrgan_path, start_batch, end_batch
        )
        print(f"✅ Батчи {start_batch}-{end_batch} успешно апскейлены")

        batches_to_perform = [f"batch_{i}" for i in range(start_batch, end_batch + 1)]
        short_video = await video.build_short_video(batches_to_perform)
        if short_video:
            await asyncio.to_thread(delete_frames, del_upscaled=True)
            print(f"🎥 Видео собрано: {short_video}")
            print(f"🗑️ Обработанные кадры удалены из батчей {start_batch}-{end_batch}")

        start_batch += threads


async def main():
    """Основной процесс обработки видео."""
    start_time = datetime.now()

    my_computer = ComputerParams()
    ai_realesrgan_path = my_computer.ai_realesrgan_path
    ai_threads, process_threads = my_computer.get_optimal_threads()

    print_header("запуск обработки видео")
    print(
        "Компоненты компьютера:",
        f"\t- ОС: {my_computer.cpu_name}",
        f"\t- Количество ядер: {my_computer.cpu_threads}",
        f"\t- Безопасные потоки (используем): {my_computer.safe_cpu_threads}",
        f"\t- Скорость SSD: ~{my_computer.ssd_speed} MB/s",
        f"\t- Оперативная память: ~{my_computer.ram_total} GB",
        f"\t- Параметры нейронок: -j {ai_threads} (загрузка:обработка:сохранение)",
        f"\t- Путь к нейронке апскейла: {ai_realesrgan_path}",
        sep="\n",
    )

    audio = AudioHandler(threads=process_threads)
    await clean_up(audio)

    # запускаем извлечение аудио из видео в фоне
    asyncio.create_task(audio.extract_audio())
    extract_frames_to_batches(process_threads)
    fps = await asyncio.to_thread(get_fps_accurate, ORIGINAL_VIDEO)
    video = VideoHandler(fps=fps)

    # Определяем диапазон батчей для обработки
    end_batch_to_upscale = calculate_batches()
    print(f"\nВсего батчей для обработки: {end_batch_to_upscale}")
    await process_batches(
        process_threads,
        ai_threads,
        video,
        ai_realesrgan_path,
        START_BATCH_TO_UPSCALE,
        end_batch_to_upscale,
    )

    await asyncio.to_thread(delete_frames, del_upscaled=False)
    print_header("финальная сборка видео")
    final_merge = video.build_final_video()

    print("\n🔊 Добавляем аудиодорожку к финальному видео...")
    audio.tmp_video_path = final_merge
    await asyncio.to_thread(audio.insert_audio)
    print(f"✅ Аудио добавлено к {FINAL_VIDEO}")

    print_header("обработка завершена")
    print(f"\n🎉 Итоговое видео сохранено: {FINAL_VIDEO}")
    end_time = datetime.now()
    print(f"⏰ Время выполнения: {end_time - start_time}")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
