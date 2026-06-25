import asyncio
import json
import subprocess

from tests.conftest import (
    configure_test_environment,
    reload_project_modules,
    require_video_tools,
)
from tests.test_smoke_video_encoding import _write_png_frames


def _probe(path):
    """Возвращает ffprobe JSON для видео и аудио"""
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=codec_type,codec_name,width,height,r_frame_rate,avg_frame_rate,nb_frames,pix_fmt",
        "-of",
        "json",
        str(path),
    ]
    return json.loads(subprocess.check_output(command, text=True))


def _stream(probe_data, codec_type):
    """Находит поток нужного типа в результате ffprobe"""
    for stream in probe_data["streams"]:
        if stream["codec_type"] == codec_type:
            return stream
    raise AssertionError(f"Поток {codec_type} не найден")


def _create_original_with_audio(frame_dir, output_path):
    """Создает маленький исходник с AAC-аудио для проверки mux copy"""
    command = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-framerate",
        "24000/1001",
        "-i",
        str(frame_dir / "frame_%08d.png"),
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:sample_rate=48000:duration=2.002",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        str(output_path),
    ]
    subprocess.run(command, check=True)


def test_video_concat_and_audio_copy_pipeline(monkeypatch, tmp_path):
    """Проверяет short-сборку, финальную склейку и копирование аудио"""
    require_video_tools()
    configure_test_environment(monkeypatch, tmp_path)
    video_handling = reload_project_modules(
        "src.config.settings",
        "src.video.video_handling",
    )[1]
    audio_handling = reload_project_modules("src.audio.audio_handling")[0]

    frame_dir = tmp_path / "source_frames"
    frame_paths = _write_png_frames(frame_dir, count=48)
    original_path = tmp_path / "original.mp4"
    final_path = tmp_path / "final.mp4"
    _create_original_with_audio(frame_dir, original_path)

    video = video_handling.VideoHandler(fps=24000 / 1001)
    first_part = video.generate_video_from_frames(frame_paths[:24], "1", "1", video.fps)
    second_part = video.generate_video_from_frames(
        frame_paths[24:], "2", "2", video.fps
    )
    merged_path = video._handle_merging([second_part, first_part])

    audio = audio_handling.AudioHandler(
        threads=2,
        input_video_path=str(original_path),
        merged_video_path=merged_path,
        output_video_path=str(final_path),
    )
    asyncio.run(audio.insert_audio())

    original_probe = _probe(original_path)
    final_probe = _probe(final_path)
    original_video = _stream(original_probe, "video")
    final_video = _stream(final_probe, "video")
    original_audio = _stream(original_probe, "audio")
    final_audio = _stream(final_probe, "audio")

    assert final_video["codec_name"] == "h264", "Видео должно остаться H.264"
    assert final_video["pix_fmt"] == "yuv444p", (
        "Финальное видео должно копировать yuv444p short без повторного encode"
    )
    assert final_audio["codec_name"] == original_audio["codec_name"], (
        "Аудио должно копироваться"
    )
    assert final_video["r_frame_rate"] == "24000/1001", "FPS не должен дрейфовать"
    assert final_video["nb_frames"] == original_video["nb_frames"] == "48"
    assert final_probe["format"]["duration"] == original_probe["format"]["duration"]


def test_default_cleanup_deletes_short_and_merged_after_success(monkeypatch, tmp_path):
    """По умолчанию short-видео и merged-видео удаляются после зависимых стадий."""
    require_video_tools()
    configure_test_environment(monkeypatch, tmp_path)
    video_handling = reload_project_modules(
        "src.config.settings",
        "src.video.video_handling",
    )[1]
    audio_handling = reload_project_modules("src.audio.audio_handling")[0]

    frame_dir = tmp_path / "source_frames"
    frame_paths = _write_png_frames(frame_dir, count=48)
    original_path = tmp_path / "original.mp4"
    final_path = tmp_path / "final.mp4"
    _create_original_with_audio(frame_dir, original_path)

    video = video_handling.VideoHandler(fps=24000 / 1001)
    first_part = video.generate_video_from_frames(frame_paths[:24], "1", "1", video.fps)
    second_part = video.generate_video_from_frames(
        frame_paths[24:], "2", "2", video.fps
    )
    video.video_queue.put(first_part)
    video.video_queue.put(second_part)

    merged_path = asyncio.run(video.build_final_video(total_short_videos=2))

    assert merged_path is not None
    assert not (tmp_path / "data" / "video_batches" / "short_1-1.mkv").exists()
    assert not (tmp_path / "data" / "video_batches" / "short_2-2.mkv").exists()
    assert (tmp_path / "data" / "tmp_video" / "merged_1-2.mp4").is_file()

    audio = audio_handling.AudioHandler(
        threads=2,
        input_video_path=str(original_path),
        merged_video_path=merged_path,
        output_video_path=str(final_path),
    )
    asyncio.run(audio.insert_audio())

    assert final_path.is_file()
    assert not (tmp_path / "data" / "tmp_video" / "merged_1-2.mp4").exists()


def test_keep_temp_files_preserves_short_and_merged_videos(monkeypatch, tmp_path):
    """KEEP_TEMP_FILES=true не должен удалять short-видео и merged-видео."""
    require_video_tools()
    configure_test_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("KEEP_TEMP_FILES", "true")
    video_handling = reload_project_modules(
        "src.config.settings",
        "src.video.video_handling",
    )[1]
    audio_handling = reload_project_modules("src.audio.audio_handling")[0]

    frame_dir = tmp_path / "source_frames"
    frame_paths = _write_png_frames(frame_dir, count=48)
    original_path = tmp_path / "original.mp4"
    final_path = tmp_path / "final.mp4"
    _create_original_with_audio(frame_dir, original_path)

    video = video_handling.VideoHandler(fps=24000 / 1001, keep_temp_files=True)
    first_part = video.generate_video_from_frames(frame_paths[:24], "1", "1", video.fps)
    second_part = video.generate_video_from_frames(
        frame_paths[24:], "2", "2", video.fps
    )
    video.video_queue.put(first_part)
    video.video_queue.put(second_part)

    merged_path = asyncio.run(video.build_final_video(total_short_videos=2))

    assert merged_path is not None
    assert (tmp_path / "data" / "video_batches" / "short_1-1.mkv").is_file()
    assert (tmp_path / "data" / "video_batches" / "short_2-2.mkv").is_file()
    assert (tmp_path / "data" / "tmp_video" / "merged_1-2.mp4").is_file()

    audio = audio_handling.AudioHandler(
        threads=2,
        input_video_path=str(original_path),
        merged_video_path=merged_path,
        output_video_path=str(final_path),
        keep_temp_files=True,
    )
    asyncio.run(audio.insert_audio())

    assert final_path.is_file()
    assert (tmp_path / "data" / "tmp_video" / "merged_1-2.mp4").is_file()
