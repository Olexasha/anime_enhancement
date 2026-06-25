from pathlib import Path

from src.config.pipeline_config import PipelineConfig, apply_preset, parse_bool


def test_defaults_are_valid_without_input_requirement():
    config = PipelineConfig.defaults()
    errors = config.validate(require_input_exists=False)
    assert errors == []
    assert config.ENABLE_DENOISE is False
    assert config.ENABLE_INTERPOLATION is True
    assert config.REALESRGAN_MODEL_NAME == "realesr-animevideov3"
    assert config.FRAMES_MULTIPLY_FACTOR == 3
    assert config.INTERMEDIATE_VIDEO_ENCODER == "libx264"
    assert config.INTERMEDIATE_VIDEO_CRF == 12
    assert config.INTERMEDIATE_VIDEO_PRESET == "medium"
    assert config.INTERMEDIATE_VIDEO_PIX_FMT == "yuv444p"
    assert config.KEEP_TEMP_FILES is False


def test_json_profile_roundtrip(tmp_path: Path):
    profile = tmp_path / "profile.json"
    config = PipelineConfig(
        ORIGINAL_VIDEO=str(tmp_path / "input.mp4"),
        FINAL_VIDEO=str(tmp_path / "out.mp4"),
        ENABLE_INTERPOLATION=False,
        KEEP_TEMP_FILES=True,
        INTERMEDIATE_VIDEO_CRF=10,
    )
    config.save_json(profile)

    loaded = PipelineConfig.from_json(profile)

    assert loaded.ORIGINAL_VIDEO == config.ORIGINAL_VIDEO
    assert loaded.FINAL_VIDEO == config.FINAL_VIDEO
    assert loaded.ENABLE_INTERPOLATION is False
    assert loaded.KEEP_TEMP_FILES is True
    assert loaded.INTERMEDIATE_VIDEO_CRF == 10


def test_env_loading(monkeypatch):
    monkeypatch.delenv("INTERMEDIATE_VIDEO_ENCODER", raising=False)
    monkeypatch.delenv("INTERMEDIATE_VIDEO_CONTAINER", raising=False)
    monkeypatch.setenv("ENABLE_DENOISE", "true")
    monkeypatch.setenv("FRAMES_PER_BATCH", "250")
    monkeypatch.setenv("INTERMEDIATE_VIDEO_PIX_FMT", "yuv444p")
    monkeypatch.setenv("KEEP_TEMP_FILES", "yes")

    config = PipelineConfig.from_env(env_file=Path("missing.env"))

    assert config.ENABLE_DENOISE is True
    assert config.FRAMES_PER_BATCH == 250
    assert config.INTERMEDIATE_VIDEO_ENCODER == "libx264"
    assert config.INTERMEDIATE_VIDEO_PIX_FMT == "yuv444p"
    assert config.INTERMEDIATE_VIDEO_CONTAINER == "mkv"
    assert config.KEEP_TEMP_FILES is True


def test_old_profile_migrates_intermediate_transport(tmp_path: Path):
    profile = tmp_path / "old_profile.json"
    profile.write_text(
        """
        {
          "version": 1,
          "settings": {
            "INTERMEDIATE_VIDEO_CRF": 0,
            "INTERMEDIATE_VIDEO_PRESET": "ultrafast",
            "INTERMEDIATE_VIDEO_PIX_FMT": "yuv444p"
          }
        }
        """,
        encoding="utf-8",
    )

    config = PipelineConfig.from_json(profile)

    assert config.INTERMEDIATE_VIDEO_ENCODER == "libx264"
    assert config.INTERMEDIATE_VIDEO_CRF == 12
    assert config.INTERMEDIATE_VIDEO_PRESET == "medium"
    assert config.INTERMEDIATE_VIDEO_PIX_FMT == "yuv444p"
    assert config.INTERMEDIATE_VIDEO_CONTAINER == "mkv"


def test_env_migrates_to_production_intermediate_transport(monkeypatch):
    monkeypatch.setenv("INTERMEDIATE_VIDEO_ENCODER", "ffv1")
    monkeypatch.setenv("INTERMEDIATE_VIDEO_PIX_FMT", "bgr0")
    monkeypatch.setenv("INTERMEDIATE_VIDEO_CRF", "14")

    config = PipelineConfig.from_env(env_file=Path("missing.env"))

    assert config.INTERMEDIATE_VIDEO_ENCODER == "libx264"
    assert config.INTERMEDIATE_VIDEO_PIX_FMT == "yuv444p"
    assert config.INTERMEDIATE_VIDEO_CRF == 12


def test_validation_detects_directory_final_video(tmp_path: Path):
    input_video = tmp_path / "input.mp4"
    input_video.write_bytes(b"fake")
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    config = PipelineConfig(
        ORIGINAL_VIDEO=str(input_video), FINAL_VIDEO=str(output_dir)
    )

    errors = config.validate(require_input_exists=True)

    assert any("FINAL_VIDEO" in error for error in errors)


def test_preset_fast_changes_resource_profile():
    config = apply_preset(PipelineConfig.defaults(), "Быстрее")

    assert config.UPSCALE_FACTOR == 2
    assert config.ENABLE_DENOISE is False


def test_max_quality_preset_enables_temporal_tta():
    config = apply_preset(PipelineConfig.defaults(), "Максимальное качество")

    assert config.ENABLE_TEMPORAL_TTA_MODE is True
    assert config.ENABLE_DENOISE is False
    assert config.INTERMEDIATE_VIDEO_ENCODER == "libx264"
    assert config.INTERMEDIATE_VIDEO_CRF == 12
    assert config.INTERMEDIATE_VIDEO_PRESET == "medium"
    assert config.INTERMEDIATE_VIDEO_PIX_FMT == "yuv444p"
    assert config.INTERMEDIATE_VIDEO_CONTAINER == "mkv"


def test_parse_bool_russian_values():
    assert parse_bool("да") is True
    assert parse_bool("нет") is False
