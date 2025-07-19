import asyncio
import os
import re
from datetime import datetime

from src.audio.audio_handling import AudioHandler
from src.config.settings import (
    END_BATCH_TO_UPSCALE,
    FINAL_VIDEO,
    INPUT_BATCHES_DIR,
    ORIGINAL_VIDEO,
    START_BATCH_TO_UPSCALE,
    STEP_PER_BATCH,
)
from src.frames.frames_helpers import extract_frames_to_batches, get_fps_accurate
from src.frames.upscale import delete_frames, upscale_batches
from src.video.video_handling import VideoHandler


def print_header(title: str) -> None:
    """Выводит заголовок программы."""
    print(f"\n{'=' * 50}")
    print(f"🎯 {title.upper()}".center(50))
    print(f"{'=' * 50}")


async def main():
    """Основной процесс обработки видео."""
    start_time = datetime.now()
    print_header("запуск обработки видео")
    audio = AudioHandler()
    await asyncio.gather(
        asyncio.to_thread(audio.delete_audio_if_exists),
        asyncio.to_thread(delete_frames, del_upscaled=False),
        asyncio.to_thread(delete_frames, del_upscaled=True),
    )

    # запускаем извлечение аудио из видео в фоне
    asyncio.create_task(audio.extract_audio())
    await asyncio.to_thread(extract_frames_to_batches)
    fps = await asyncio.to_thread(get_fps_accurate, ORIGINAL_VIDEO)
    video = VideoHandler(fps=fps)

    # Определяем диапазон батчей для обработки
    start_batch = START_BATCH_TO_UPSCALE
    end_batch = 0
    if END_BATCH_TO_UPSCALE == 0:
        batch_name_pattern = re.compile(r"batch_(\d+)")
        end_batch_to_upscale = len(
            [
                batch
                for batch in os.listdir(INPUT_BATCHES_DIR)
                if batch_name_pattern.match(batch)
            ]
        )
    else:
        end_batch_to_upscale = END_BATCH_TO_UPSCALE
    print(f"\nВсего батчей для обработки: {end_batch_to_upscale}")

    print(f"🚀 Начинаем обработку с шагом {STEP_PER_BATCH} батчей...")
    while end_batch != end_batch_to_upscale:
        if start_batch + STEP_PER_BATCH <= end_batch_to_upscale:
            # если шаг STEP_PER_BATCH доступен в диапазоне, то берем его
            end_batch = start_batch + STEP_PER_BATCH - 1
        else:
            # иначе берем все оставшиеся батчи до конца
            end_batch = end_batch_to_upscale

        print(f"\n🔄 Обрабатываем батчи с {start_batch} по {end_batch}...")

        # Запуск апскейла батчей с фреймами
        await upscale_batches(start_batch, end_batch)
        print(f"✅ Батчи {start_batch}-{end_batch} успешно апскейлены")

        batches_to_perform = [f"batch_{i}" for i in range(start_batch, end_batch + 1)]
        short_video = await video.build_short_video(batches_to_perform)
        if short_video:
            await asyncio.to_thread(delete_frames, del_upscaled=True)
            print(f"🎥 Видео собрано: {short_video}")
            print(f"🗑️ Обработанные кадры удалены из батчей {start_batch}-{end_batch}")

        start_batch += STEP_PER_BATCH

    await asyncio.to_thread(delete_frames, del_upscaled=False)
    print_header("финальная сборка видео")
    # Сборка финального видео из временных видео
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
