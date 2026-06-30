import asyncio
from pathlib import Path

from tests.conftest import configure_test_environment, reload_project_modules


def test_recommended_settings_defaults(monkeypatch, tmp_path):
    """Проверяет рекомендуемые дефолты качества без чтения реального .env"""
    configure_test_environment(monkeypatch, tmp_path)
    monkeypatch.delenv("ENABLE_INTERPOLATION", raising=False)
    monkeypatch.delenv("ENABLE_DENOISE", raising=False)
    monkeypatch.delenv("DENOISE_FACTOR", raising=False)
    monkeypatch.delenv("UPSCALE_FACTOR", raising=False)
    monkeypatch.delenv("INTERMEDIATE_VIDEO_CRF", raising=False)

    settings = reload_project_modules("src.config.settings")[0]

    assert settings.ENABLE_INTERPOLATION is True, "Интерполяция должна быть включена"
    assert settings.ENABLE_DENOISE is False, "Денойз должен оставаться ручной опцией"
    assert settings.DENOISE_FACTOR == 3
    assert settings.UPSCALE_FACTOR > 1, "Если апскейл меньше 1, то он не работает"
    assert settings.INTERMEDIATE_VIDEO_CRF == 12
    assert settings.INTERMEDIATE_VIDEO_PRESET == "medium"
    assert settings.INTERMEDIATE_VIDEO_PIX_FMT == "yuv444p"


def test_ffmpeg_fps_is_formatted_as_fraction(monkeypatch, tmp_path):
    """Проверяет, что FPS уходит в ffmpeg дробью, а не округленным float"""
    configure_test_environment(monkeypatch, tmp_path)
    video_handling = reload_project_modules(
        "src.config.settings",
        "src.video.video_handling",
    )[1]

    assert video_handling.VideoHandler._format_ffmpeg_fps(24000 / 1001) == "24000/1001"
    assert video_handling.VideoHandler._format_ffmpeg_fps(48000 / 1001) == "48000/1001"
    assert video_handling.VideoHandler._format_ffmpeg_fps(24) == "24/1"


def test_short_video_default_encoder_args_are_compact_h264(monkeypatch, tmp_path):
    configure_test_environment(monkeypatch, tmp_path)
    video_handling = reload_project_modules(
        "src.config.settings",
        "src.video.video_handling",
    )[1]

    args = video_handling.VideoHandler._intermediate_video_encoder_args()

    assert args == [
        "-pix_fmt",
        "yuv444p",
        "-color_range",
        "tv",
        "-colorspace",
        "bt709",
        "-color_primaries",
        "bt709",
        "-color_trc",
        "bt709",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-tune",
        "animation",
        "-crf",
        "12",
    ]


def test_default_short_video_builder_limit_is_two(monkeypatch, tmp_path):
    configure_test_environment(monkeypatch, tmp_path)
    video_handling = reload_project_modules(
        "src.config.settings",
        "src.video.video_handling",
    )[1]

    video = video_handling.VideoHandler(fps=24)

    assert video.max_short_video_builders == 2


def test_sort_video_paths_by_batch_start():
    """Проверяет, что порядок short-файлов не зависит от порядка очереди."""
    from src.video.video_helpers import sort_video_paths

    paths = [
        r"D:\tmp\short_10-12.mkv",
        r"D:\tmp\short_1-3.mkv",
        r"D:\tmp\short_4-6.mp4",
    ]

    assert sort_video_paths(paths) == [
        r"D:\tmp\short_1-3.mkv",
        r"D:\tmp\short_4-6.mp4",
        r"D:\tmp\short_10-12.mkv",
    ]


def test_sort_frame_paths_by_frame_number():
    """Проверяет, что кадры сортируются по числу, а не строкой."""
    from src.video.video_helpers import sort_frame_paths

    paths = [
        r"D:\tmp\frame_10.png",
        r"D:\tmp\frame_2.png",
        r"D:\tmp\frame_1.png",
    ]

    assert sort_frame_paths(paths) == [
        r"D:\tmp\frame_1.png",
        r"D:\tmp\frame_2.png",
        r"D:\tmp\frame_10.png",
    ]


def test_batch_window_keeps_upscale_width_and_chunks_rife():
    from main import (
        calculate_interpolation_workers,
        calculate_short_video_windows,
        choose_batch_window_size,
    )

    assert calculate_interpolation_workers(6) == 2
    assert choose_batch_window_size(6, enable_interpolation=True) == 6
    assert calculate_short_video_windows(1, 6, 6) == 1
    assert choose_batch_window_size(4, enable_interpolation=True) == 4
    assert choose_batch_window_size(2, enable_interpolation=True) == 2
    assert choose_batch_window_size(1, enable_interpolation=True) == 1
    assert choose_batch_window_size(9, enable_interpolation=True) == 9
    assert choose_batch_window_size(6, enable_interpolation=False) == 6


def test_existing_temp_children_skips_gitkeep(tmp_path):
    from main import _existing_temp_children

    temp_dir = tmp_path / "data" / "video_batches"
    temp_dir.mkdir(parents=True)
    (temp_dir / ".gitkeep").write_text("", encoding="utf-8")
    short_file = temp_dir / "short_1-1.mkv"
    short_file.write_bytes(b"video")

    assert _existing_temp_children([str(temp_dir)]) == [short_file]


def _complete_progress(progress):
    progress.mark_fixed_step_done("prepare", "prepare")
    progress.update_frame_stage(
        "extract", done_frames=progress.total_source_frames, status="extract"
    )
    if progress.enable_denoise:
        progress.update_frame_stage(
            "denoise", done_frames=progress.total_source_frames, status="denoise"
        )
    progress.update_frame_stage(
        "upscale", done_frames=progress.total_source_frames, status="upscale"
    )
    if progress.enable_interpolation:
        progress.update_frame_stage(
            "interpolate",
            done_frames=progress.total_interpolated_frames,
            status="interpolate",
        )
    progress.update_short_videos_done(progress.total_windows, "short")
    progress.mark_fixed_step_done("final_merge", "final")
    progress.mark_fixed_step_done("cleanup", "cleanup")
    progress.mark_fixed_step_done("audio", "audio")
    return progress.mark_fixed_step_done("done", "done")


def test_pipeline_progress_is_monotonic_and_skips_disabled_denoise():
    from main import PipelineProgress

    progress = PipelineProgress(
        enable_denoise=False,
        enable_interpolation=True,
        video_total_frames=6000,
        start_batch=1,
        end_batch=6,
        batch_size=1000,
        total_windows=6,
        frames_multiply_factor=3,
    )

    assert "denoise" not in progress.work_totals

    values = [
        progress.mark_fixed_step_done("prepare", "prepare"),
        progress.update_frame_stage("extract", done_frames=1000, status="extract"),
        progress.update_frame_stage("upscale", done_frames=1000, status="upscale"),
        progress.update_frame_stage("upscale", done_frames=250, status="upscale"),
        progress.update_frame_stage(
            "interpolate", done_frames=3000, status="interpolate"
        ),
        progress.update_short_videos_done(1, "short"),
    ]

    assert values == sorted(values)
    assert values[-1] < 100


def test_pipeline_progress_tracks_denoise_and_interpolation_work():
    from main import PipelineProgress

    progress = PipelineProgress(
        enable_denoise=True,
        enable_interpolation=True,
        video_total_frames=2000,
        start_batch=1,
        end_batch=2,
        batch_size=1000,
        total_windows=2,
        frames_multiply_factor=3,
    )

    assert "denoise" in progress.work_totals
    assert "interpolate" in progress.work_totals
    assert progress.total_source_frames == 2000
    assert progress.total_interpolated_frames == 6000
    assert progress.output_frames_for_batches(2, 2) == 3000


def test_pipeline_progress_without_interpolation_reaches_100_only_after_fixed_steps():
    from main import PipelineProgress

    progress = PipelineProgress(
        enable_denoise=True,
        enable_interpolation=False,
        video_total_frames=1200,
        start_batch=1,
        end_batch=2,
        batch_size=1000,
        total_windows=2,
        frames_multiply_factor=3,
    )

    assert "interpolate" not in progress.work_totals

    progress.mark_fixed_step_done("prepare", "prepare")
    progress.update_frame_stage(
        "extract", done_frames=progress.total_source_frames, status="extract"
    )
    progress.update_frame_stage(
        "denoise", done_frames=progress.total_source_frames, status="denoise"
    )
    progress.update_frame_stage(
        "upscale", done_frames=progress.total_source_frames, status="upscale"
    )
    progress.update_short_videos_done(progress.total_windows, "short")

    assert progress.value() < 100

    progress.mark_fixed_step_done("final_merge", "final")
    progress.mark_fixed_step_done("cleanup", "cleanup")

    assert progress.value() < 100
    assert progress.mark_fixed_step_done("audio", "audio") < 100
    assert progress.mark_fixed_step_done("done", "done") == 100


def test_pipeline_progress_short_video_keeps_fixed_steps_visible():
    from main import PipelineProgress

    progress = PipelineProgress(
        enable_denoise=False,
        enable_interpolation=False,
        video_total_frames=24,
        start_batch=1,
        end_batch=1,
        batch_size=1000,
        total_windows=1,
    )

    prepare_value = progress.mark_fixed_step_done("prepare", "prepare")

    assert 0 < prepare_value < 25
    assert _complete_progress(progress) == 100


def test_pipeline_progress_first_window_does_not_jump_too_far():
    from main import PipelineProgress

    progress = PipelineProgress(
        enable_denoise=False,
        enable_interpolation=True,
        video_total_frames=6000,
        start_batch=1,
        end_batch=6,
        batch_size=1000,
        total_windows=6,
        frames_multiply_factor=3,
    )

    progress.mark_fixed_step_done("prepare", "prepare")
    progress.update_frame_stage("extract", done_frames=1000, status="extract")
    progress.update_frame_stage("upscale", done_frames=1000, status="upscale")
    progress.update_frame_stage("interpolate", done_frames=3000, status="interpolate")
    progress.update_short_videos_done(1, "short")

    assert progress.value() < 35


def test_process_batches_keeps_one_short_per_window_and_chunks_rife(
    monkeypatch, tmp_path
):
    configure_test_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("ENABLE_INTERPOLATION", "true")
    monkeypatch.setenv("FRAMES_MULTIPLY_FACTOR", "3")
    settings, improve, main = reload_project_modules(
        "src.config.settings",
        "src.frames.improve",
        "main",
    )
    calls = []

    for batch_num in range(1, 7):
        batch_dir = Path(settings.INPUT_BATCHES_DIR) / f"batch_{batch_num}"
        batch_dir.mkdir(parents=True, exist_ok=True)
        (batch_dir / "frame_00000001.png").write_bytes(b"frame")

    async def fake_improve_batches(
        processing_type,
        process_threads,
        ai_threads,
        ai_tool_path,
        start_batch,
        end_batch,
        max_retries=3,
        progress_callback=None,
    ):
        _ = ai_threads, ai_tool_path, max_retries
        calls.append(
            (
                processing_type.value,
                process_threads,
                start_batch,
                end_batch,
            )
        )
        output_dir = {
            improve.ProcessingType.UPSCALE: settings.UPSCALED_BATCHES_DIR,
            improve.ProcessingType.INTERPOLATE: settings.INTERPOLATED_BATCHES_DIR,
        }[processing_type]
        for batch_num in range(start_batch, end_batch + 1):
            batch_dir = Path(output_dir) / f"batch_{batch_num}"
            batch_dir.mkdir(parents=True, exist_ok=True)
            (batch_dir / "frame_00000001.png").write_bytes(b"frame")
        if progress_callback:
            progress_callback(100)

    class FakeVideo:
        def __init__(self):
            self.short_calls = []

        def build_short_video(self, batches):
            self.short_calls.append(batches)

    video = FakeVideo()
    monkeypatch.setattr(improve, "improve_batches", fake_improve_batches)
    monkeypatch.setattr(main, "emit_gui_progress", lambda *args, **kwargs: None)

    asyncio.run(
        main.process_batches(
            6,
            "2:2:2",
            video,
            "waifu2x.exe",
            "realesrgan.exe",
            "rife.exe",
            1,
            6,
            main.PipelineProgress(
                enable_denoise=False,
                enable_interpolation=True,
                video_total_frames=6 * settings.FRAMES_PER_BATCH,
                start_batch=1,
                end_batch=6,
                batch_size=settings.FRAMES_PER_BATCH,
                total_windows=1,
                frames_multiply_factor=settings.FRAMES_MULTIPLY_FACTOR,
            ),
        )
    )

    assert calls == [
        ("upscale", 6, 1, 6),
        ("interpolate", 2, 1, 2),
        ("interpolate", 2, 3, 4),
        ("interpolate", 2, 5, 6),
    ]
    assert video.short_calls == [
        ["batch_1", "batch_2", "batch_3", "batch_4", "batch_5", "batch_6"]
    ]


def test_short_video_builder_is_throttled(monkeypatch, tmp_path):
    configure_test_environment(monkeypatch, tmp_path)
    video_handling = reload_project_modules(
        "src.config.settings",
        "src.video.video_handling",
    )[1]
    created = []

    class FakeProcess:
        def __init__(self, target, args):
            self.target = target
            self.args = args
            self.exitcode = None
            self.alive = False
            self.join_calls = 0
            created.append(self)

        def start(self):
            self.alive = True

        def is_alive(self):
            return self.alive

        def join(self, timeout=None):
            self.join_calls += 1
            self.alive = False
            self.exitcode = 0

    monkeypatch.setattr(video_handling.multiprocessing, "Process", FakeProcess)
    video = video_handling.VideoHandler(fps=24, max_short_video_builders=1)

    video.build_short_video(["batch_1"])
    video.build_short_video(["batch_2"])

    assert len(created) == 2
    assert created[0].join_calls >= 1
    assert video.short_videos_requested == 2
