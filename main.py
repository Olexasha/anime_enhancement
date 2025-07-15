import asyncio
import os
from datetime import datetime

from src.audio.audio_handling import extract_audio, insert_audio
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


def main():
    """Основной процесс обработки видео."""
    start_time = datetime.now()
    print_header("запуск обработки видео")

    print("\n📹 Получаем FPS исходного видео...")
    fps = get_fps_accurate(ORIGINAL_VIDEO)
    print(f"✅ FPS видео: {fps}")

    print("\n🔊 Извлекаем аудиодорожку...")
    audio = extract_audio()
    if audio:
        print(f"✅ Аудио извлечено: {audio}")
    else:
        print("⚠️ Аудиодорожка не найдена")

    print("\n🎞️ Извлекаем кадры из видео...")
    extract_frames_to_batches()
    print("✅ Кадры успешно извлечены")

    print("\n🛠️ Инициализируем сборщик видео...")
    tmp_builder = VideoHandler(fps=fps)
    print(f"✅ Сборщик готов (FPS: {fps})")

    # Определяем диапазон батчей для обработки
    start_batch = START_BATCH_TO_UPSCALE
    end_batch = 0
    if END_BATCH_TO_UPSCALE == 0:
        end_batch_to_upscale = len(os.listdir(INPUT_BATCHES_DIR)) - 1  # -1 для .gitkeep
    else:
        end_batch_to_upscale = END_BATCH_TO_UPSCALE
    print(f"\n🔢 Всего батчей для обработки: {end_batch_to_upscale}")

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
        asyncio.run(upscale_batches(start_batch, end_batch))
        print(f"✅ Батчи {start_batch}-{end_batch} успешно апскейлены")

        batches_to_perform = [f"batch_{i}" for i in range(start_batch, end_batch + 1)]
        short_video = tmp_builder.process_frames_to_video(batches_to_perform)
        if short_video:
            delete_frames(del_upscaled=True)
            print(f"🎥 Видео собрано: {short_video}")
            print(f"🗑️ Удалены обработанные кадры")

        start_batch += STEP_PER_BATCH

    print_header("финальная сборка видео")
    delete_frames(del_upscaled=False)
    # Сборка финального видео из временных видео
    final_merge = tmp_builder.build_final_video()

    if audio:
        print("\n🔊 Добавляем аудиодорожку к финальному видео...")
        insert_audio(audio, fps, video_path=final_merge, output_path=FINAL_VIDEO)
        print(f"✅ Аудио добавлено к {FINAL_VIDEO}")
    else:
        print("\n🔇 Финальное видео сохранено без звука")

    print_header("обработка завершена")
    print(f"\n🎉 Итоговое видео сохранено: {FINAL_VIDEO}")
    end_time = datetime.now()
    print(f"⏰ Время выполнения: {end_time - start_time}")
    print("=" * 50)


if __name__ == "__main__":
    main()
