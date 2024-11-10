import glob
import os
import shutil
import asyncio
import ffmpeg
from moviepy.editor import VideoFileClip, concatenate_videoclips

from src.config.settings import (
    BATCH_VIDEO_PATH,
    END_BATCH_TO_UPSCALE,
    FINAL_VIDEO,
    INPUT_BATCHES_DIR,
    ORIGINAL_VIDEO,
    OUTPUT_BATCHES_DIR,
    START_BATCH_TO_UPSCALE,
    STEP_PER_BATCH,
    TMP_FINAL_VIDEO,
)
from src.video_processing.audio import extract_audio, insert_audio
from src.video_processing.frames import get_fps_accurate, extract_frames_to_batches
from src.video_processing.upscale import upscale_batches


def merge_frames_to_video(batches_list, video_batch_num, fps):
    """Собирает обработанные фреймы в видео."""
    try:
        # собираем все апскейленные фреймы из нескольких батчей в 1 список
        batches_and_frames_list = list()
        for batch in batches_list:
            batch_path = f"{OUTPUT_BATCHES_DIR}/{batch}"
            batches_and_frames_list.append(
                sorted(glob.glob(os.path.join(batch_path, "frame*.jpg")))
            )
        frames_list = sum(batches_and_frames_list, [])

        # файл чтобы скормить пути фреймов ffmpeg
        frames_file_path = os.path.join("./", "frames_list.txt")
        with open(frames_file_path, "w") as f:
            for frame in frames_list:
                f.write(f"file '{frame}'\n")

        batch_video = os.path.join(
            BATCH_VIDEO_PATH, f"batch_{video_batch_num}.mp4"
        )
        ffmpeg.input(frames_file_path, format="concat", safe=0).output(
            batch_video, vcodec="libx264", pix_fmt="yuv420p", crf=18, r=fps
        ).run()
        os.remove(frames_file_path)
        print(f"Партия {batches_list} собрана в видео.")
        return batch_video
    except Exception as e:
        print(f"Ошибка сборки видео из фреймов: {e}")
        return None


def combine_videos(tmp_final_video, batch_video, fps):
    """Объединяет партии видео в одно целое."""
    try:
        if os.path.isfile(tmp_final_video):
            first_clip = VideoFileClip(tmp_final_video)
            second_clip = VideoFileClip(batch_video)
            combined_clip = concatenate_videoclips([first_clip, second_clip])
            combined_clip.write_videofile(FINAL_VIDEO, codec="libx264", fps=fps)
            print(f"Объединение видеофайлов завершено.")

            first_clip.close()
            second_clip.close()
            combined_clip.close()
            os.unlink(batch_video)
            os.unlink(tmp_final_video)
            os.rename(FINAL_VIDEO, tmp_final_video)
        else:
            shutil.move(batch_video, tmp_final_video)
    except Exception as e:
        print(f"Ошибка при объединении видеофайлов: {e}")


def main():
    """Основной процесс обработки видео."""
    fps = get_fps_accurate(ORIGINAL_VIDEO)
    audio = extract_audio()
    extract_frames_to_batches()

    start_batch = START_BATCH_TO_UPSCALE
    end_batch = 0

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

        # После улучшения фреймов собираем видео
        # if MERGE_ALL_BATCHES_TO_VIDEO:
        #     batches_to_perform = os.listdir(OUTPUT_BATCHES_DIR)
        #     batches_to_perform.sort(key=compare_strings)
        # else:
        #     batches_to_perform = [f"batch_{i}" for i in range(start_batch, end_batch)]
        # batch_video = merge_frames_to_video(
        #     batches_to_perform, counter_of_video_batches
        # )
        # if batch_video:
        #     delete_upscaled_frames()
        #     combine_videos(TMP_FINAL_VIDEO, batch_video)
        #     counter_of_video_batches += 1
        #     print(
        #         f"Партия фреймов {batch_num // 4 + 1} успешно обработана и объединена."
        #     )

        start_batch += STEP_PER_BATCH

    if audio:
        insert_audio(audio, fps)
    else:
        print("Звуковой файл не найден, финальное видео сохранено без звука.")

    print(f"Обработка завершена. Итоговое видео сохранено в {TMP_FINAL_VIDEO}")


if __name__ == "__main__":
    main()
