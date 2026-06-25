import subprocess

from tests.conftest import (
    configure_test_environment,
    reload_project_modules,
    require_video_tools,
)
from tests.test_smoke_video_encoding import _write_png_frames


def _create_video_from_frames(frame_dir, output_path):
    command = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-framerate",
        "24",
        "-i",
        str(frame_dir / "frame_%08d.png"),
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        str(output_path),
    ]
    subprocess.run(command, check=True)


def test_windowed_extraction_writes_only_requested_batches(monkeypatch, tmp_path):
    require_video_tools()
    configure_test_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("FRAMES_PER_BATCH", "3")
    frames_helpers = reload_project_modules(
        "src.config.settings",
        "src.frames.frames_helpers",
    )[1]

    frame_dir = tmp_path / "source_frames"
    _write_png_frames(frame_dir, count=8)
    video_path = tmp_path / "input.mp4"
    _create_video_from_frames(frame_dir, video_path)
    output_dir = tmp_path / "data" / "default_frame_batches"

    saved = frames_helpers.extract_frame_batches_range(
        threads=2,
        start_batch=2,
        end_batch=2,
        video_path=str(video_path),
        output_dir=str(output_dir),
        batch_size=3,
    )

    assert saved == 3
    assert not (output_dir / "batch_1").exists()
    assert sorted(path.name for path in (output_dir / "batch_2").glob("*.png")) == [
        "frame_00000004.png",
        "frame_00000005.png",
        "frame_00000006.png",
    ]
    assert not (output_dir / "batch_3").exists()
