from tests.conftest import configure_test_environment, reload_project_modules


def test_recommended_settings_defaults(monkeypatch, tmp_path):
    """Проверяет рекомендуемые дефолты качества без чтения реального .env"""
    configure_test_environment(monkeypatch, tmp_path)
    monkeypatch.delenv("ENABLE_INTERPOLATION", raising=False)
    monkeypatch.delenv("ENABLE_DENOISE", raising=False)
    monkeypatch.delenv("DENOISE_FACTOR", raising=False)
    monkeypatch.delenv("UPSCALE_FACTOR", raising=False)
    monkeypatch.delenv("VIDEO_CRF", raising=False)
    monkeypatch.delenv("VIDEO_TUNE", raising=False)
    monkeypatch.delenv("VIDEO_PIX_FMT", raising=False)

    settings = reload_project_modules("src.config.settings")[0]

    assert settings.ENABLE_INTERPOLATION is True, "Интерполяция должна быть включена"
    assert settings.ENABLE_DENOISE is False, "Денойз должен оставаться ручной опцией"
    assert settings.DENOISE_FACTOR == 3
    assert settings.UPSCALE_FACTOR > 1, "Если апскейл меньше 1, то он не работает"
    assert settings.VIDEO_CRF == 10
    assert settings.VIDEO_TUNE == "animation"
    assert settings.VIDEO_PIX_FMT == "yuv444p"


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
