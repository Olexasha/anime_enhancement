import os

from dotenv import load_dotenv

load_dotenv(verbose=True)
ROOT_DIR = os.getcwd()

# Пути к файлам
ORIGINAL_VIDEO = os.path.join(ROOT_DIR, "data", "input_video", "naruto_test2.mkv")
AUDIO_PATH = os.path.join(ROOT_DIR, "data", "audio")
TMP_VIDEO_PATH = os.path.join(ROOT_DIR, "data", "tmp_video")
FINAL_VIDEO = os.path.join(
    ROOT_DIR,
    "data",
    "output_video",
    f"{os.path.splitext(os.path.basename(ORIGINAL_VIDEO))[0]}_enhanced.mp4",
)
BATCH_VIDEO_PATH = os.path.join(ROOT_DIR, "data", "video_batches")
INPUT_BATCHES_DIR = os.path.join(ROOT_DIR, "data", "default_frame_batches")
LOGS_DIR = os.path.join(ROOT_DIR)
OUTPUT_IMAGE_FORMAT = os.getenv("OUTPUT_IMAGE_FORMAT", "png")
START_BATCH_TO_IMPROVE = int(os.getenv("START_BATCH_TO_UPSCALE", 1))
END_BATCH_TO_IMPROVE = int(os.getenv("END_BATCH_TO_UPSCALE", 0))
FRAMES_PER_BATCH = int(os.getenv("FRAMES_PER_BATCH", 1000))

# Настройка апскейла
RESOLUTION = os.getenv("RESOLUTION", "4K")
UPSCALED_BATCHES_DIR = os.path.join(ROOT_DIR, "data", "upscaled_frame_batches")
REALESRGAN_MODEL_DIR = os.path.join(ROOT_DIR, "src", "utils", "realesrgan", "models")
REALESRGAN_MODEL_NAME = os.getenv("REALESRGAN_MODEL_NAME", "realesr-animevideov3")
UPSCALE_FACTOR = int(os.getenv("UPSCALE_FACTOR", 2))

# Настройка денойза
DENOISED_BATCHES_DIR = os.path.join(ROOT_DIR, "data", "denoised_frame_batches")
DENOISE_FACTOR = int(os.getenv("DENOISE_FACTOR", 3))
WAIFU2X_UPSCALE_FACTOR = int(os.getenv("WAIFU2X_UPSCALE_FACTOR", 1))
if WAIFU2X_UPSCALE_FACTOR > 1:
    WAIFU2X_MODEL_DIR = os.path.join(
        ROOT_DIR,
        "src",
        "utils",
        "waifu2x",
        "models",
        "models-upconv_7_anime_style_art_rgb",
    )
else:
    WAIFU2X_MODEL_DIR = os.path.join(
        ROOT_DIR, "src", "utils", "waifu2x", "models", "models-cunet"
    )

# Настройка интерполяции
INTERPOLATED_BATCHES_DIR = os.path.join(ROOT_DIR, "data", "interpolated_frame_batches")
FRAMES_MULTIPLY_FACTOR = int(os.getenv("FRAMES_MULTIPLY_FACTOR", 4))
TIME_STEP = round(1 / FRAMES_MULTIPLY_FACTOR, 2)
if FRAMES_MULTIPLY_FACTOR > 2:
    RIFE_MODEL_DIR = os.path.join(
        ROOT_DIR, "src", "utils", "rife", "models", "rife-v4.6"
    )
else:
    RIFE_MODEL_DIR = os.path.join(
        ROOT_DIR, "src", "utils", "rife", "models", "rife-anime"
    )
ENABLE_UHD_MODE = os.getenv("ENABLE_UHD_MODE", True).lower() == "true"
ENABLE_SPATIAL_TTA_MODE = os.getenv("ENABLE_SPATIAL_TTA_MODE", False).lower() == "true"
ENABLE_TEMPORAL_TTA_MODE = (
    os.getenv("ENABLE_TEMPORAL_TTA_MODE", False).lower() == "true"
)
