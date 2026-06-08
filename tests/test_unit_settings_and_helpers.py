from tests.conftest import configure_test_environment, reload_project_modules


def test_recommended_settings_defaults(monkeypatch, tmp_path):
    """Проверяет рекомендуемые дефолты качества без чтения реального .env"""
    configure_test_environment(monkeypatch, tmp_path)
    monkeypatch.delenv("ENABLE_INTERPOLATION", raising=False)
    monkeypatch.delenv("ENABLE_DENOISE", raising=False)
    monkeypatch.delenv("UPSCALE_FACTOR", raising=False)

    settings = reload_project_modules("src.config.settings")[0]

    assert settings.ENABLE_INTERPOLATION is True, "Интерполяция должна быть включена"
    assert settings.ENABLE_DENOISE is False, "Денойз не должен включаться по умолчанию"
    assert settings.UPSCALE_FACTOR > 1, "Если апскейл меньше 1, то он не работает"


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


def test_sort_video_paths_by_batch_start():
    """Проверяет, что порядок short-файлов не зависит от порядка очереди."""
    from src.video.video_helpers import sort_video_paths

    paths = [
        r"D:\tmp\short_10-12.mp4",
        r"D:\tmp\short_1-3.mp4",
        r"D:\tmp\short_4-6.mp4",
    ]

    assert sort_video_paths(paths) == [
        r"D:\tmp\short_1-3.mp4",
        r"D:\tmp\short_4-6.mp4",
        r"D:\tmp\short_10-12.mp4",
    ]
