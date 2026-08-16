import subprocess
from pathlib import Path

import cv2
import numpy as np

from src.frames.scene_cut_guard import (
    SceneCut,
    SceneCutPlan,
    build_scene_segments,
    detect_scene_cuts,
    write_scene_cut_debug,
)
from tests.conftest import configure_test_environment, reload_project_modules


def _write_synthetic_scene_frames(directory: Path) -> list[str]:
    directory.mkdir(parents=True, exist_ok=True)
    frame_paths = []
    colors = [
        (210, 230, 255),
        (212, 229, 255),
        (211, 231, 254),
        (213, 230, 255),
        (12, 18, 35),
        (13, 17, 36),
        (14, 19, 35),
        (12, 18, 34),
    ]
    for index, color in enumerate(colors, start=1):
        frame = np.full((72, 128, 3), color, dtype=np.uint8)
        path = directory / f"frame_{index:08d}.png"
        cv2.imwrite(str(path), frame)
        frame_paths.append(str(path))
    return frame_paths


def test_histogram_scene_cut_detection_finds_day_to_night_cut(tmp_path):
    frame_paths = _write_synthetic_scene_frames(tmp_path / "frames")

    cuts = detect_scene_cuts(
        frame_paths,
        method="histogram",
        threshold=0.42,
        min_scene_frames=4,
    )

    assert [(cut.from_frame, cut.to_frame) for cut in cuts] == [(4, 5)]
    assert cuts[0].score >= 0.42


def test_scene_segments_do_not_include_cross_scene_pair(tmp_path):
    frame_paths = _write_synthetic_scene_frames(tmp_path / "frames")
    cuts = [SceneCut(from_frame=4, to_frame=5, score=0.9)]

    segments = build_scene_segments(frame_paths, cuts)

    assert [(segment.start_frame, segment.end_frame) for segment in segments] == [
        (1, 4),
        (5, 8),
    ]
    segment_pairs = {
        (Path(left).name, Path(right).name)
        for segment in segments
        for left, right in zip(
            segment.frame_paths,
            segment.frame_paths[1:],
            strict=False,
        )
    }
    assert ("frame_00000004.png", "frame_00000005.png") not in segment_pairs


def test_scene_cut_debug_json_is_written_and_deduplicated(tmp_path):
    report_path = tmp_path / "scene_cuts.json"
    cuts = [SceneCut(from_frame=4, to_frame=5, score=0.87654321)]

    write_scene_cut_debug(
        report_path=report_path,
        enabled=True,
        requested_method="auto",
        method="histogram",
        threshold=0.42,
        min_scene_frames=4,
        cuts=cuts,
    )
    write_scene_cut_debug(
        report_path=report_path,
        enabled=True,
        requested_method="auto",
        method="histogram",
        threshold=0.42,
        min_scene_frames=4,
        cuts=cuts,
    )

    payload = report_path.read_text(encoding="utf-8")

    assert '"enabled": true' in payload
    assert '"method": "histogram"' in payload
    assert payload.count('"from_frame"') == 1


def test_rife_scene_guard_runs_independent_segments(monkeypatch, tmp_path):
    configure_test_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("ENABLE_INTERPOLATION", "true")
    monkeypatch.setenv("FRAMES_MULTIPLY_FACTOR", "3")
    settings, improve = reload_project_modules(
        "src.config.settings",
        "src.frames.improve",
    )

    input_dir = Path(settings.UPSCALED_BATCHES_DIR) / "batch_1"
    output_dir = Path(settings.INTERPOLATED_BATCHES_DIR) / "batch_1"
    frame_paths = _write_synthetic_scene_frames(input_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    seen_segment_means = []

    def fake_run_ai_command(command, **_kwargs):
        input_arg = Path(command[command.index("-i") + 1])
        output_arg = Path(command[command.index("-o") + 1])
        frames = sorted(input_arg.glob("*.png"))
        means = [float(cv2.imread(str(frame)).mean()) for frame in frames]
        seen_segment_means.append(means)
        for index in range(len(frames) * settings.FRAMES_MULTIPLY_FACTOR):
            (output_arg / f"{index + 1:08d}.png").write_bytes(b"fake-rife-frame")

    monkeypatch.setattr(improve, "_run_ai_command", fake_run_ai_command)

    improve._improve_interpolation_batch_with_scene_cut_guard(
        ai_threads="1:1:1",
        ai_tool_path="rife.exe",
        batch_num=1,
        input_dir=input_dir,
        output_dir=output_dir,
        scene_cut_plan=SceneCutPlan(
            cuts=(SceneCut(from_frame=4, to_frame=5, score=0.9),),
        ),
        max_retries=1,
    )

    assert len(seen_segment_means) == 2
    assert all(all(value > 100 for value in means) for means in seen_segment_means[:1])
    assert all(all(value < 100 for value in means) for means in seen_segment_means[1:])
    assert len(list(output_dir.glob("*.png"))) == len(frame_paths) * 3


def test_ai_command_retries_after_nonzero_exit(monkeypatch):
    from src.frames import improve

    attempts = []

    def fake_run(command, **kwargs):
        attempts.append((command, kwargs))
        if len(attempts) == 1:
            raise subprocess.CalledProcessError(1, command, stderr="temporary failure")

    monkeypatch.setattr(improve.subprocess, "run", fake_run)
    monkeypatch.setattr(improve.time, "sleep", lambda _seconds: None)

    improve._run_ai_command(
        ["tool.exe", "--flag"],
        config={"display_name": "Тест"},
        batch_num=1,
        max_retries=2,
    )

    assert len(attempts) == 2
    assert all(kwargs["check"] is True for _, kwargs in attempts)
