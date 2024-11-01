import glob
import os
import subprocess
from moviepy.editor import VideoFileClip, concatenate_videoclips
import shutil
import ffmpeg

from config import (
    END_BATCH_TO_UPSCALE,
    TMP_FINAL_VIDEO,
    FRAMES_PER_BATCH,
    INPUT_BATCHES_DIR,
    ORIGINAL_AUDIO,
    OUTPUT_BATCHES_DIR,
    START_BATCH_TO_UPSCALE,
    STEP_PER_BATCH, MERGE_ALL_BATCHES_TO_VIDEO, FPS, BATCH_VIDEO_PATH, FINAL_VIDEO,
)


def upscale_batches(start_batch, end_batch):
    """Запускает скрипт для улучшения батчей в заданном диапазоне."""
    current_dir = os.getcwd()
    cmd = [
        "/bin/bash",
        f"{current_dir}/enhance_frames.sh",
        str(start_batch),
        str(end_batch),
    ]
    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    for line in process.stdout:
        print(line, end="")
    process.wait()
    if process.returncode == 0:
        print(f"Батчи с {start_batch} по {end_batch} успешно обработаны.")
    else:
        print(
            f"Ошибка при обработке батчей {start_batch}-{end_batch}: {process.stderr.read()}"
        )


def merge_frames_to_video(batches_list, counter_of_video_batches):
    """Собирает обработанные фреймы в видео."""
    try:
        batches_and_frames_list = list()
        for batch in batches_list:
            batch_path = f"{OUTPUT_BATCHES_DIR}/{batch}"
            batches_and_frames_list.append(sorted(glob.glob(os.path.join(batch_path, "frame*.jpg"))))
        frames_list = sum(batches_and_frames_list, [])

        # файл чтобы скормить пути фреймов ffmpeg
        frames_file_path = os.path.join("./", "frames_list.txt")
        with open(frames_file_path, "w") as f:
            for frame in frames_list:
                f.write(f"file '{frame}'\n")

        batch_video = os.path.join(BATCH_VIDEO_PATH, f"batch_{counter_of_video_batches}.mp4")
        ffmpeg.input(frames_file_path, format="concat", safe=0).output(
            batch_video, vcodec="libx264", pix_fmt="yuv420p", crf=18, r=FPS
        ).run()
        os.remove(frames_file_path)
        print(f"Партия {batches_list} собрана в видео.")
        return batch_video
    except Exception as e:
        print(f"Ошибка сборки видео из фреймов: {e}")
        return None


def delete_upscaled_frames(del_only_dirs=True):
    """Удаляет обработанные фреймы."""
    file_paths = glob.glob(os.path.join(OUTPUT_BATCHES_DIR, '*'))
    for file_path in file_paths:
        try:
            if os.path.isdir(file_path):
                shutil.rmtree(file_path)
            if not del_only_dirs and os.path.isfile(file_path) or os.path.islink(file_path):
                os.remove(file_path)
        except Exception as e:
            print(f"Не удалось удалить {file_path}. Причина: {e}")


def combine_videos(tmp_final_video, batch_video):
    """Объединяет партии видео в одно целое."""
    try:
        if os.path.isfile(tmp_final_video):
            first_clip = VideoFileClip(tmp_final_video)
            second_clip = VideoFileClip(batch_video)
            combined_clip = concatenate_videoclips([first_clip, second_clip])
            combined_clip.write_videofile(FINAL_VIDEO, codec="libx264", fps=FPS)
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


def add_audio(final_video_path, audio_file):
    """Наложение звука на финальное видео."""
    try:
        final_with_audio = final_video_path.replace(".mp4", "_with_audio.mp4")
        ffmpeg.input(final_video_path).input(audio_file).output(
            final_with_audio, vcodec="copy", acodec="aac", strict="experimental"
        ).run()
        print(f"Финальное видео с наложением звука сохранено в {final_with_audio}")
    except Exception as e:
        print(f"Ошибка при наложении звука: {e}")


def compare_strings(s):
    num = int(s.split("_")[-1]) if "_" in s else int(s)
    return num


def main():
    """Основной процесс обработки видео."""
    counter_of_video_batches = START_BATCH_TO_UPSCALE // STEP_PER_BATCH + 1
    start_batch_to_upscale = START_BATCH_TO_UPSCALE

    if END_BATCH_TO_UPSCALE == 0:
        input_batches = os.listdir(INPUT_BATCHES_DIR)
        total_batches = len(input_batches)
        input_batches.sort(key=compare_strings)
        frames_in_last_batch = len(
            glob.glob(f"{INPUT_BATCHES_DIR}/{input_batches[-1]}/*jpg")
        )
        end_batch_to_upscale = (
            FRAMES_PER_BATCH * total_batches - 1 + frames_in_last_batch
        )
    else:
        end_batch_to_upscale = END_BATCH_TO_UPSCALE

    for batch_num in range(
        start_batch_to_upscale, end_batch_to_upscale, STEP_PER_BATCH
    ):
        start_batch = batch_num
        end_batch = min(batch_num + STEP_PER_BATCH - 1, end_batch_to_upscale)

        # Запуск обработки батчей
        upscale_batches(start_batch, end_batch)

        # После улучшения фреймов собираем видео
        if MERGE_ALL_BATCHES_TO_VIDEO:
            batches_to_perform = os.listdir(OUTPUT_BATCHES_DIR)
            batches_to_perform.sort(key=compare_strings)
        else:
            batches_to_perform = [f"batch_{i}" for i in range(start_batch, end_batch)]
        batch_video = merge_frames_to_video(batches_to_perform, counter_of_video_batches)
        if batch_video:
            delete_upscaled_frames()
            combine_videos(TMP_FINAL_VIDEO, batch_video)
            counter_of_video_batches += 1
            print(
                f"Партия фреймов {batch_num // 4 + 1} успешно обработана и объединена."
            )

    if os.path.isfile(ORIGINAL_AUDIO):
        add_audio(TMP_FINAL_VIDEO, ORIGINAL_AUDIO)
    else:
        print("Звуковой файл не найден, финальное видео сохранено без звука.")

    print(f"Обработка завершена. Итоговое видео сохранено в {TMP_FINAL_VIDEO}")


if __name__ == "__main__":
    main()
