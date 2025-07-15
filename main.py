import asyncio
import os

from src.config.settings import (
    END_BATCH_TO_UPSCALE,
    FINAL_VIDEO,
    INPUT_BATCHES_DIR,
    ORIGINAL_VIDEO,
    START_BATCH_TO_UPSCALE,
    STEP_PER_BATCH,
)
from src.video_processing.audio import extract_audio, insert_audio
from src.video_processing.frames import extract_frames_to_batches, get_fps_accurate
from src.video_processing.upscale import delete_frames, upscale_batches
from src.video_processing.video_assembly import VideoHandler


def main():
    """Основной процесс обработки видео."""
    fps = get_fps_accurate(ORIGINAL_VIDEO)
    audio = extract_audio()
    extract_frames_to_batches()

    start_batch = START_BATCH_TO_UPSCALE
    end_batch = 0
    # Экземпляр tmp видео ~32 минуты, обновляется после ~32 минут
    tmp_builder = VideoHandler(fps=fps)

    if END_BATCH_TO_UPSCALE == 0:
        # -1 потому что файл .gitkeep в INPUT_BATCHES_DIR тоже считается
        end_batch_to_upscale = len(os.listdir(INPUT_BATCHES_DIR)) - 1
    else:
        end_batch_to_upscale = END_BATCH_TO_UPSCALE

    while end_batch != end_batch_to_upscale:
        if start_batch + STEP_PER_BATCH <= end_batch_to_upscale:
            # если шаг STEP_PER_BATCH доступен в диапазоне, то берем его
            end_batch = start_batch + STEP_PER_BATCH - 1
        else:
            # иначе берем все оставшиеся батчи до конца
            end_batch = end_batch_to_upscale

        # Запуск апскейла батчей с фреймами
        asyncio.run(upscale_batches(start_batch, end_batch))

        batches_to_perform = [f"batch_{i}" for i in range(start_batch, end_batch + 1)]
        short_video = tmp_builder.process_frames_to_video(batches_to_perform)
        if short_video:
            delete_frames(del_upscaled=True)
            print(f"Партия фреймов {short_video} успешно обработана и объединена.")
        start_batch += STEP_PER_BATCH

    delete_frames(del_upscaled=False)
    # Сборка финального видео из временных видео
    final_merge = tmp_builder.build_final_video()

    if audio:
        insert_audio(audio, fps, video_path=final_merge, output_path=FINAL_VIDEO)
    else:
        print("Звуковой файл не найден, финальное видео сохранено без звука.")

    print(f"Обработка завершена. Итоговое видео сохранено в {FINAL_VIDEO}")


if __name__ == "__main__":
    main()
