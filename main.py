import asyncio
import os

from src.config.settings import (
    END_BATCH_TO_UPSCALE,
    FINAL_VIDEO,
    INPUT_BATCHES_DIR,
    ORIGINAL_VIDEO,
    START_BATCH_TO_UPSCALE,
    STEP_PER_BATCH,
    TMP_VIDEO_PATH,
)
from src.video_processing.audio import extract_audio, insert_audio
from src.video_processing.frames import (
    extract_frames_to_batches,
    get_fps_accurate,
)
from src.video_processing.upscale import delete_upscaled_frames, upscale_batches
from src.video_processing.video_assembly import VideoHandler


def main():
    """Основной процесс обработки видео."""
    tmp_final_video = os.path.join(TMP_VIDEO_PATH, "tmp_final_video.mp4")

    fps = get_fps_accurate(ORIGINAL_VIDEO)
    audio = extract_audio()
    extract_frames_to_batches()

    start_batch = START_BATCH_TO_UPSCALE
    end_batch = 0
    tmp_videos_counter = 1
    tmp_builder = VideoHandler(fps=fps, tmp_video_name=f"tmp_video_{tmp_videos_counter}")

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

        # Запуск обработки батчей
        asyncio.run(upscale_batches(start_batch, end_batch))

        batches_to_perform = [f"batch_{i}" for i in range(start_batch, end_batch + 1)]
        short_video = tmp_builder.process_frames_to_video(batches_to_perform)
        if short_video:
            delete_upscaled_frames()
            print(
                f"Партия фреймов {short_video} успешно обработана и объединена."
            )
        if tmp_builder.current_short_video_count == tmp_builder.MAX_SHORT_VIDEOS:
            tmp_videos_counter += 1
            tmp_builder = VideoHandler(fps=fps, tmp_video_name=f"tmp_video_{tmp_videos_counter}")

        start_batch += STEP_PER_BATCH

    if audio:
        insert_audio(audio, fps, video_path=tmp_final_video, output_path=FINAL_VIDEO)
    else:
        print("Звуковой файл не найден, финальное видео сохранено без звука.")

    print(f"Обработка завершена. Итоговое видео сохранено в {FINAL_VIDEO}")


if __name__ == "__main__":
    main()
