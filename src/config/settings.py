from __future__ import annotations

from pathlib import Path

from src.config.pipeline_config import PipelineConfig
from src.config.runtime_paths import default_data_dir, logs_parent_dir, resource_path

_CONFIG = PipelineConfig.from_env()

DATA_ROOT = default_data_dir()
ORIGINAL_VIDEO = _CONFIG.ORIGINAL_VIDEO
FINAL_VIDEO = _CONFIG.FINAL_VIDEO

AUDIO_PATH = str(DATA_ROOT / "audio")
TMP_VIDEO_PATH = str(DATA_ROOT / "tmp_video")
BATCH_VIDEO_PATH = str(DATA_ROOT / "video_batches")
INPUT_BATCHES_DIR = str(DATA_ROOT / "default_frame_batches")
LOGS_DIR = str(logs_parent_dir())

OUTPUT_IMAGE_FORMAT = _CONFIG.OUTPUT_IMAGE_FORMAT.lower()
START_BATCH_TO_IMPROVE = _CONFIG.START_BATCH_TO_IMPROVE
END_BATCH_TO_IMPROVE = _CONFIG.END_BATCH_TO_IMPROVE
FRAMES_PER_BATCH = _CONFIG.FRAMES_PER_BATCH
ENABLE_DENOISE = _CONFIG.ENABLE_DENOISE
ENABLE_INTERPOLATION = _CONFIG.ENABLE_INTERPOLATION
KEEP_TEMP_FILES = _CONFIG.KEEP_TEMP_FILES
LOG_LEVEL = _CONFIG.LOG_LEVEL

RESOLUTION = _CONFIG.RESOLUTION
UPSCALED_BATCHES_DIR = str(DATA_ROOT / "upscaled_frame_batches")
REALESRGAN_MODEL_DIR = str(resource_path("src/utils/realesrgan/models"))
REALESRGAN_MODEL_NAME = _CONFIG.REALESRGAN_MODEL_NAME
UPSCALE_FACTOR = _CONFIG.UPSCALE_FACTOR

VIDEO_ENCODER = _CONFIG.VIDEO_ENCODER.lower()
VIDEO_CRF = _CONFIG.VIDEO_CRF
VIDEO_PRESET = _CONFIG.VIDEO_PRESET
VIDEO_NVENC_CQ = _CONFIG.VIDEO_NVENC_CQ
VIDEO_PIX_FMT = _CONFIG.VIDEO_PIX_FMT

DENOISED_BATCHES_DIR = str(DATA_ROOT / "denoised_frame_batches")
DENOISE_FACTOR = _CONFIG.DENOISE_FACTOR
WAIFU2X_UPSCALE_FACTOR = _CONFIG.WAIFU2X_UPSCALE_FACTOR
if WAIFU2X_UPSCALE_FACTOR > 1:
    WAIFU2X_MODEL_DIR = str(
        resource_path("src/utils/waifu2x/models/models-upconv_7_anime_style_art_rgb")
    )
else:
    WAIFU2X_MODEL_DIR = str(
        resource_path("src/utils/waifu2x/models/models-cunet")
    )

INTERPOLATED_BATCHES_DIR = str(DATA_ROOT / "interpolated_frame_batches")
FRAMES_MULTIPLY_FACTOR = _CONFIG.FRAMES_MULTIPLY_FACTOR
TIME_STEP = round(1 / max(1, FRAMES_MULTIPLY_FACTOR), 2)
if FRAMES_MULTIPLY_FACTOR > 2:
    RIFE_MODEL_DIR = str(resource_path("src/utils/rife/models/rife-v4.6"))
else:
    RIFE_MODEL_DIR = str(resource_path("src/utils/rife/models/rife-anime"))
ENABLE_UHD_MODE = _CONFIG.ENABLE_UHD_MODE
ENABLE_SPATIAL_TTA_MODE = _CONFIG.ENABLE_SPATIAL_TTA_MODE
ENABLE_TEMPORAL_TTA_MODE = _CONFIG.ENABLE_TEMPORAL_TTA_MODE


def ensure_data_dirs() -> None:
    """Создает рабочие папки проекта, если их еще нет."""
    for path in (
        str(DATA_ROOT),
        str(Path(ORIGINAL_VIDEO).expanduser().parent),
        str(Path(FINAL_VIDEO).expanduser().parent),
        AUDIO_PATH,
        TMP_VIDEO_PATH,
        BATCH_VIDEO_PATH,
        INPUT_BATCHES_DIR,
        UPSCALED_BATCHES_DIR,
        DENOISED_BATCHES_DIR,
        INTERPOLATED_BATCHES_DIR,
    ):
        Path(path).mkdir(parents=True, exist_ok=True)


ensure_data_dirs()
