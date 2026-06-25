import json
import subprocess

from tests.conftest import (
    configure_test_environment,
    reload_project_modules,
    require_video_tools,
)


def _write_png_frames(directory, count=5, size=(160, 90)):
    """Создает простые PNG-кадры для проверки видеосборки"""
    import cv2
    import numpy as np

    directory.mkdir(parents=True, exist_ok=True)
    frame_paths = []
    width, height = size
    for index in range(count):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:, :, 0] = (20 + index * 20) % 256
        frame[:, :, 1] = 60
        frame[:, :, 2] = 120
        cv2.putText(
            frame,
            str(index + 1),
            (width // 3, height // 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        frame_path = directory / f"frame_{index + 1:08d}.png"
        cv2.imwrite(str(frame_path), frame)
        frame_paths.append(str(frame_path))
    return frame_paths


def _probe_video(path):
    """Возвращает ffprobe JSON для первого видеопотока."""
    command = [
        "ffprobe",
        "-v",
        "error",
        "-count_frames",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_name,width,height,avg_frame_rate,nb_read_frames,pix_fmt",
        "-of",
        "json",
        str(path),
    ]
    return json.loads(subprocess.check_output(command, text=True))["streams"][0]


def test_generate_video_from_frames_smoke(monkeypatch, tmp_path):
    """Проверяет smoke-сборку short-видео"""
    require_video_tools()
    configure_test_environment(monkeypatch, tmp_path)
    video_handling = reload_project_modules(
        "src.config.settings",
        "src.video.video_handling",
    )[1]

    frame_paths = _write_png_frames(tmp_path / "frames", count=5)
    video_path = video_handling.VideoHandler.generate_video_from_frames(
        frame_paths,
        "1",
        "1",
        24000 / 1001,
    )
    video_stream = _probe_video(video_path)

    assert video_path.endswith(".mkv"), "Short-видео должно писаться в MKV"
    assert video_stream["codec_name"] == "h264", "Short-видео должно быть H.264"
    assert video_stream["pix_fmt"] == "yuv444p", (
        "Short-видео должно сохранять 4:4:4 цвет без chroma subsampling"
    )
    assert video_stream["avg_frame_rate"] == "24000/1001", (
        "FPS должен сохраняться дробью"
    )
    assert video_stream["nb_read_frames"] == "5", "Количество кадров должно совпадать"

    decoded = tmp_path / "decoded_frame_1.png"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            video_path,
            "-frames:v",
            "1",
            str(decoded),
        ],
        check=True,
    )

    import cv2

    source_frame = cv2.imread(frame_paths[0])
    decoded_frame = cv2.imread(str(decoded))
    assert decoded_frame.shape == source_frame.shape
    assert cv2.PSNR(source_frame, decoded_frame) > 35, (
        "Компактное short-видео должно оставаться визуально близким к PNG-кадрам"
    )
