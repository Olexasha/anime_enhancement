from pathlib import Path

from tests.conftest import configure_test_environment, reload_project_modules


def _write_file(path: Path, payload: bytes = b"data") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def test_cleanup_does_not_delete_dangerous_paths(monkeypatch, tmp_path):
    configure_test_environment(monkeypatch, tmp_path)
    cleanup = reload_project_modules("src.config.settings", "src.utils.cleanup")[1]

    data_root = tmp_path / "data"
    result = cleanup.cleanup_path(data_root, "тест опасного пути")

    assert result.skipped
    assert data_root.exists()

    home_result = cleanup.cleanup_path(Path.home(), "тест home directory")

    assert home_result.skipped
    assert Path.home().exists()


def test_cleanup_deletes_only_allowed_temp_paths(monkeypatch, tmp_path):
    configure_test_environment(monkeypatch, tmp_path)
    cleanup = reload_project_modules("src.config.settings", "src.utils.cleanup")[1]

    allowed_batch = tmp_path / "data" / "upscaled_frame_batches" / "batch_1"
    outside_dir = tmp_path / "outside"
    _write_file(allowed_batch / "frame_00000001.png")
    _write_file(outside_dir / "keep.txt")

    summary = cleanup.cleanup_many(
        [allowed_batch, outside_dir],
        "тест удаления только разрешенных временных путей",
    )

    assert summary.results[0].deleted
    assert summary.results[1].skipped
    assert not allowed_batch.exists()
    assert outside_dir.exists()


def test_keep_temp_files_blocks_stage_cleanup(monkeypatch, tmp_path):
    configure_test_environment(monkeypatch, tmp_path)
    cleanup = reload_project_modules("src.config.settings", "src.utils.cleanup")[1]

    rife_batch = tmp_path / "data" / "interpolated_frame_batches" / "batch_1"
    dependency = tmp_path / "data" / "video_batches" / "short_1-1.mkv"
    _write_file(rife_batch / "frame_00000001.png")
    _write_file(dependency)

    summary = cleanup.maybe_cleanup_after_stage(
        stage="Батч 1",
        paths=[rife_batch],
        reason="short-video успешно создан",
        keep_temp_files=True,
        dependency_path=dependency,
    )

    assert summary.skipped
    assert rife_batch.exists()


def test_mock_success_short_video_allows_rife_cleanup(monkeypatch, tmp_path):
    configure_test_environment(monkeypatch, tmp_path)
    cleanup = reload_project_modules("src.config.settings", "src.utils.cleanup")[1]

    rife_batch = tmp_path / "data" / "interpolated_frame_batches" / "batch_1"
    short_video = tmp_path / "data" / "video_batches" / "short_1-1.mkv"
    _write_file(rife_batch / "frame_00000001.png")
    monkeypatch.setattr(cleanup, "verify_video_readable", lambda *args, **kwargs: True)

    summary = cleanup.maybe_cleanup_after_stage(
        stage="Батч 1",
        paths=[rife_batch],
        reason="short-video успешно создан, удаляем RIFE-кадры батча",
        keep_temp_files=False,
        dependency_path=short_video,
        dependency_is_video=True,
    )

    assert summary.deleted_paths == 1
    assert not rife_batch.exists()


def test_missing_or_empty_output_blocks_previous_stage_cleanup(monkeypatch, tmp_path):
    configure_test_environment(monkeypatch, tmp_path)
    cleanup = reload_project_modules("src.config.settings", "src.utils.cleanup")[1]

    upscaled_batch = tmp_path / "data" / "upscaled_frame_batches" / "batch_1"
    empty_output = tmp_path / "data" / "video_batches" / "short_1-1.mkv"
    _write_file(upscaled_batch / "frame_00000001.png")
    _write_file(empty_output, b"")

    summary = cleanup.maybe_cleanup_after_stage(
        stage="Батч 1",
        paths=[upscaled_batch],
        reason="short-video успешно создан",
        keep_temp_files=False,
        dependency_path=empty_output,
    )

    assert summary.skipped
    assert upscaled_batch.exists()
