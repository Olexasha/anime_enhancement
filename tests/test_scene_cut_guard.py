import subprocess
from pathlib import Path

import cv2
import numpy as np
import pytest

from src.frames.scene_cut_guard import (
    SceneCut,
    SceneCutPlan,
    StaticSceneRun,
    analyze_scene_frames,
    build_guard_segments,
    build_scene_segments,
    build_static_frame_map,
    calculate_static_scene_min_run_frames,
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


def _write_static_run_frames(directory: Path, frame_count: int = 20) -> list[str]:
    directory.mkdir(parents=True, exist_ok=True)
    frame_paths = []
    base = np.full((72, 128, 3), (80, 120, 180), dtype=np.uint8)
    for index in range(1, frame_count + 1):
        frame = base.copy()
        if 5 <= index <= 16:
            offset = (index - 5) % 4
            frame[10 + offset, 20 + offset] = (92, 132, 192)
            frame[30 + offset, 50 + offset] = (92, 132, 192)
        else:
            frame[:, : index * 3 % 100 + 1] = (10, 20, 30)
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


def test_static_scene_detection_accepts_only_long_near_identical_run(tmp_path):
    frame_paths = _write_static_run_frames(tmp_path / "frames")

    _, static_runs = analyze_scene_frames(
        frame_paths,
        method="histogram",
        threshold=0.42,
        min_scene_frames=4,
    )

    assert static_runs == [StaticSceneRun(start_frame=5, end_frame=16)]


def test_static_scene_detection_rejects_small_local_motion(tmp_path):
    frame_dir = tmp_path / "frames"
    frame_dir.mkdir()
    frame_paths = []
    for index in range(14):
        frame = np.full((360, 640, 3), 80, dtype=np.uint8)
        left = 20 + index * 8
        frame[120:125, left : left + 5] = 230
        path = frame_dir / f"frame_{index + 1:08d}.png"
        cv2.imwrite(str(path), frame)
        frame_paths.append(str(path))

    _, static_runs = analyze_scene_frames(
        frame_paths,
        method="histogram",
        threshold=0.42,
        min_scene_frames=4,
    )

    assert static_runs == []


def test_static_scene_detection_rejects_blink_inside_static_shot(tmp_path):
    frame_dir = tmp_path / "frames"
    frame_dir.mkdir()
    frame_paths = []
    for index in range(1, 21):
        frame = np.full((180, 320, 3), 150, dtype=np.uint8)
        if index == 10:
            frame[70:75, 145:155] = 30
        path = frame_dir / f"frame_{index:08d}.png"
        cv2.imwrite(str(path), frame)
        frame_paths.append(str(path))

    _, static_runs = analyze_scene_frames(
        frame_paths,
        method="histogram",
        threshold=0.42,
        min_scene_frames=4,
        static_min_run_frames=12,
    )

    assert static_runs == []


def test_static_scene_detection_rejects_very_slow_pan(tmp_path):
    frame_dir = tmp_path / "frames"
    frame_dir.mkdir()
    x = np.arange(320, dtype=np.uint8)
    textured_row = ((x // 8) % 2 * 180 + 30).astype(np.uint8)
    base = np.repeat(textured_row[np.newaxis, :], 180, axis=0)
    base = cv2.merge((base, np.roll(base, 3, axis=1), np.roll(base, 7, axis=1)))
    frame_paths = []
    for index in range(24):
        frame = np.roll(base, index // 4, axis=1)
        path = frame_dir / f"frame_{index + 1:08d}.png"
        cv2.imwrite(str(path), frame)
        frame_paths.append(str(path))

    _, static_runs = analyze_scene_frames(
        frame_paths,
        method="histogram",
        threshold=0.42,
        min_scene_frames=4,
        static_min_run_frames=12,
    )

    assert static_runs == []


def test_static_scene_detection_rejects_slow_cumulative_drift(tmp_path):
    frame_dir = tmp_path / "frames"
    frame_dir.mkdir()
    frame_paths = []
    for index in range(12):
        frame = np.full((180, 320, 3), 100, dtype=np.uint8)
        changed_pixels = index * 8
        frame.reshape(-1, 3)[:changed_pixels] = 120
        path = frame_dir / f"frame_{index + 1:08d}.png"
        cv2.imwrite(str(path), frame)
        frame_paths.append(str(path))

    _, static_runs = analyze_scene_frames(
        frame_paths,
        method="histogram",
        threshold=0.42,
        min_scene_frames=4,
        static_min_run_frames=12,
    )

    assert static_runs == []


def test_static_run_never_crosses_scene_cut(tmp_path):
    frame_dir = tmp_path / "frames"
    frame_dir.mkdir()
    frame_paths = []
    for index in range(1, 31):
        value = 220 if index <= 15 else 25
        frame = np.full((180, 320, 3), value, dtype=np.uint8)
        path = frame_dir / f"frame_{index:08d}.png"
        cv2.imwrite(str(path), frame)
        frame_paths.append(str(path))

    cuts, static_runs = analyze_scene_frames(
        frame_paths,
        method="histogram",
        threshold=0.42,
        min_scene_frames=4,
        static_min_run_frames=15,
    )

    assert [(cut.from_frame, cut.to_frame) for cut in cuts] == [(15, 16)]
    assert static_runs == [
        StaticSceneRun(start_frame=1, end_frame=15),
        StaticSceneRun(start_frame=16, end_frame=30),
    ]
    assert all(not (run.start_frame <= 15 < run.end_frame) for run in static_runs)


def test_static_minimum_run_uses_source_fps_duration():
    assert calculate_static_scene_min_run_frames(24000 / 1001, 0.5) == 12
    assert calculate_static_scene_min_run_frames(30.0, 0.5) == 15
    assert calculate_static_scene_min_run_frames(60.0, 0.5) == 30
    assert calculate_static_scene_min_run_frames(None, 0.5) == 12


def test_guard_segments_keep_motion_boundaries_around_static_run(tmp_path):
    frame_paths = _write_static_run_frames(tmp_path / "frames")

    segments = build_guard_segments(
        frame_paths,
        cuts=(),
        static_runs=(StaticSceneRun(start_frame=5, end_frame=16),),
    )

    assert [
        (segment.start_frame, segment.end_frame, segment.is_static)
        for segment in segments
    ] == [
        (1, 5, False),
        (6, 15, True),
        (16, 20, False),
    ]


def test_static_frame_map_uses_first_frame_as_representative(tmp_path):
    frame_paths = _write_static_run_frames(tmp_path / "frames")

    duplicate_map = build_static_frame_map(
        frame_paths,
        (StaticSceneRun(start_frame=5, end_frame=16),),
    )

    assert len(duplicate_map) == 11
    assert {Path(path).name for path in duplicate_map.values()} == {
        "frame_00000005.png"
    }
    assert Path(frame_paths[4]).name not in {Path(path).name for path in duplicate_map}


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
        static_runs=(StaticSceneRun(start_frame=10, end_frame=21),),
    )
    write_scene_cut_debug(
        report_path=report_path,
        enabled=True,
        requested_method="auto",
        method="histogram",
        threshold=0.42,
        min_scene_frames=4,
        cuts=cuts,
        static_runs=(StaticSceneRun(start_frame=10, end_frame=21),),
    )

    payload = report_path.read_text(encoding="utf-8")

    assert '"enabled": true' in payload
    assert '"method": "histogram"' in payload
    assert payload.count('"from_frame"') == 1
    assert payload.count('"start_frame"') == 1
    assert '"frame_count": 12' in payload


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


def test_static_guard_upscales_one_representative_per_run(monkeypatch, tmp_path):
    configure_test_environment(monkeypatch, tmp_path)
    settings, improve = reload_project_modules(
        "src.config.settings",
        "src.frames.improve",
    )
    input_dir = Path(settings.INPUT_BATCHES_DIR) / "batch_1"
    output_dir = Path(settings.UPSCALED_BATCHES_DIR) / "batch_1"
    frame_paths = _write_static_run_frames(input_dir)
    ai_tool = tmp_path / "realesrgan.exe"
    ai_tool.write_bytes(b"test tool")
    processed_names = []

    def fake_run_ai_command(command, **_kwargs):
        command_input = Path(command[command.index("-i") + 1])
        command_output = Path(command[command.index("-o") + 1])
        command_output.mkdir(parents=True, exist_ok=True)
        for frame in sorted(command_input.glob("*.png")):
            processed_names.append(frame.name)
            (command_output / frame.name).write_bytes(frame.read_bytes())

    monkeypatch.setattr(improve, "_run_ai_command", fake_run_ai_command)

    improve._improve_batch(
        improve.ProcessingType.UPSCALE,
        "1:1:1",
        str(ai_tool),
        1,
        scene_cut_plan=SceneCutPlan(
            cuts=(),
            static_runs=(StaticSceneRun(start_frame=5, end_frame=16),),
        ),
    )

    assert len(processed_names) == len(frame_paths) - 11
    assert "frame_00000005.png" in processed_names
    assert "frame_00000006.png" not in processed_names
    output_frames = sorted(output_dir.glob("*.png"))
    assert len(output_frames) == len(frame_paths)
    assert output_frames[4].read_bytes() == output_frames[15].read_bytes()
    assert output_frames[4].stat().st_nlink >= 12


def test_hardlink_failure_falls_back_to_independent_copy(monkeypatch, tmp_path):
    configure_test_environment(monkeypatch, tmp_path)
    _, improve = reload_project_modules(
        "src.config.settings",
        "src.frames.improve",
    )
    source = tmp_path / "source.png"
    target = tmp_path / "target.png"
    source.write_bytes(b"source-frame")

    def fail_hardlink(*_args, **_kwargs):
        raise OSError("hardlinks unavailable")

    monkeypatch.setattr(improve.os, "link", fail_hardlink)

    improve._link_or_copy_frame(source, target)

    assert target.read_bytes() == b"source-frame"
    target.write_bytes(b"changed-copy")
    assert source.read_bytes() == b"source-frame"


def test_static_guard_skips_rife_inside_static_run(monkeypatch, tmp_path):
    configure_test_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("ENABLE_INTERPOLATION", "true")
    monkeypatch.setenv("FRAMES_MULTIPLY_FACTOR", "3")
    settings, improve = reload_project_modules(
        "src.config.settings",
        "src.frames.improve",
    )
    monkeypatch.setattr(
        improve,
        "STATIC_RIFE_MIN_SAVED_MEGAPIXEL_FRAMES_PER_EXTRA_PROCESS",
        0.0,
    )
    input_dir = Path(settings.UPSCALED_BATCHES_DIR) / "batch_1"
    output_dir = Path(settings.INTERPOLATED_BATCHES_DIR) / "batch_1"
    frame_paths = _write_static_run_frames(input_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    processed_segment_lengths = []

    def fake_run_ai_command(command, **_kwargs):
        command_input = Path(command[command.index("-i") + 1])
        command_output = Path(command[command.index("-o") + 1])
        frames = sorted(command_input.glob("*.png"))
        processed_segment_lengths.append(len(frames))
        for index in range(len(frames) * settings.FRAMES_MULTIPLY_FACTOR):
            (command_output / f"{index + 1:08d}.png").write_bytes(b"rife")

    monkeypatch.setattr(improve, "_run_ai_command", fake_run_ai_command)

    improve._improve_interpolation_batch_with_scene_cut_guard(
        ai_threads="1:1:1",
        ai_tool_path="rife.exe",
        batch_num=1,
        input_dir=input_dir,
        output_dir=output_dir,
        scene_cut_plan=SceneCutPlan(
            cuts=(),
            static_runs=(StaticSceneRun(start_frame=5, end_frame=16),),
        ),
        max_retries=1,
    )

    assert processed_segment_lengths == [5, 5]
    assert sum(processed_segment_lengths) == len(frame_paths) - 10
    output_frame_count = len(list(output_dir.glob("*.png")))
    assert output_frame_count == len(frame_paths) * 3
    source_fps = 30
    output_fps = source_fps * settings.FRAMES_MULTIPLY_FACTOR
    assert output_frame_count / output_fps == pytest.approx(
        len(frame_paths) / source_fps
    )


def test_static_guard_avoids_unprofitable_extra_rife_processes(monkeypatch, tmp_path):
    configure_test_environment(monkeypatch, tmp_path)
    _, improve = reload_project_modules(
        "src.config.settings",
        "src.frames.improve",
    )
    frame_paths = _write_static_run_frames(tmp_path / "frames")

    segments, optimization_bypassed = improve._build_profitable_interpolation_segments(
        frame_paths,
        SceneCutPlan(
            cuts=(),
            static_runs=(StaticSceneRun(start_frame=5, end_frame=16),),
        ),
    )

    assert [
        (segment.start_frame, segment.end_frame, segment.is_static)
        for segment in segments
    ] == [(1, 20, False)]
    assert optimization_bypassed is True


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
