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


def test_json_profile_roundtrip(tmp_path: Path):
    profile = tmp_path / "profile.json"
    config = PipelineConfig(
        ORIGINAL_VIDEO=str(tmp_path / "input.mp4"),
        FINAL_VIDEO=str(tmp_path / "out.mp4"),
        ENABLE_INTERPOLATION=False,
        VIDEO_ENCODER="h264_nvenc",
        VIDEO_NVENC_CQ=15,
    )
    config.save_json(profile)

    loaded = PipelineConfig.from_json(profile)

    assert loaded.ORIGINAL_VIDEO == config.ORIGINAL_VIDEO
    assert loaded.FINAL_VIDEO == config.FINAL_VIDEO
    assert loaded.ENABLE_INTERPOLATION is False
    assert loaded.VIDEO_ENCODER == "h264_nvenc"
    assert loaded.VIDEO_NVENC_CQ == 15


def test_env_loading(monkeypatch):
    monkeypatch.setenv("ENABLE_DENOISE", "true")
    monkeypatch.setenv("FRAMES_PER_BATCH", "250")
    monkeypatch.setenv("VIDEO_CRF", "17")

    config = PipelineConfig.from_env(env_file=Path("missing.env"))

    assert config.ENABLE_DENOISE is True
    assert config.FRAMES_PER_BATCH == 250
    assert config.VIDEO_CRF == 17


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


def test_preset_fast_changes_encoder():
    config = apply_preset(PipelineConfig.defaults(), "Быстрее")

    assert config.VIDEO_ENCODER == "h264_nvenc"
    assert config.ENABLE_DENOISE is False


def test_max_quality_preset_enables_temporal_tta():
    config = apply_preset(PipelineConfig.defaults(), "Максимальное качество")

    assert config.ENABLE_TEMPORAL_TTA_MODE is True


def test_parse_bool_russian_values():
    assert parse_bool("да") is True
    assert parse_bool("нет") is False
