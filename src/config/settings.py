import os

try:
    from dotenv import load_dotenv
except ImportError:

    def load_dotenv(verbose: bool = False) -> bool:
        """Пропускает загрузку .env, если python-dotenv сломался"""
        return False


load_dotenv(verbose=True)
ROOT_DIR = os.getcwd()

ORIGINAL_VIDEO = os.getenv(
    "ORIGINAL_VIDEO",
    os.path.join(
        "D:\\",
        "Anime",
        "Naruto - Перерождение",
        "Глава 13",
        "Эпизод 1 - Возвращение.mp4",
    ),
)
FINAL_VIDEO = os.getenv(
    "FINAL_VIDEO",
    os.path.join(
        "D:\\",
        "Anime",
        "Naruto - Перерождение",
        "Глава 13",
        f"{os.path.splitext(os.path.basename(ORIGINAL_VIDEO))[0]}_enhanced.mp4",
    ),
)

AUDIO_PATH = os.path.join(ROOT_DIR, "data", "audio")
TMP_VIDEO_PATH = os.path.join(ROOT_DIR, "data", "tmp_video")

BATCH_VIDEO_PATH = os.path.join(ROOT_DIR, "data", "video_batches")
INPUT_BATCHES_DIR = os.path.join(ROOT_DIR, "data", "default_frame_batches")
LOGS_DIR = os.path.join(ROOT_DIR)
OUTPUT_IMAGE_FORMAT = os.getenv("OUTPUT_IMAGE_FORMAT", "png")
START_BATCH_TO_IMPROVE = int(
    os.getenv("START_BATCH_TO_IMPROVE", os.getenv("START_BATCH_TO_UPSCALE", 1))
)
END_BATCH_TO_IMPROVE = int(
    os.getenv("END_BATCH_TO_IMPROVE", os.getenv("END_BATCH_TO_UPSCALE", 0))
)
FRAMES_PER_BATCH = int(os.getenv("FRAMES_PER_BATCH", 1000))
ENABLE_DENOISE = os.getenv("ENABLE_DENOISE", "false").lower() == "true"
ENABLE_INTERPOLATION = os.getenv("ENABLE_INTERPOLATION", "true").lower() == "true"

# Настройка апскейла
RESOLUTION = os.getenv("RESOLUTION", "4K")
UPSCALED_BATCHES_DIR = os.path.join(ROOT_DIR, "data", "upscaled_frame_batches")
REALESRGAN_MODEL_DIR = os.path.join(ROOT_DIR, "src", "utils", "realesrgan", "models")
REALESRGAN_MODEL_NAME = os.getenv("REALESRGAN_MODEL_NAME", "realesr-animevideov3")
UPSCALE_FACTOR = int(os.getenv("UPSCALE_FACTOR", 3))

# Настройка кодирования видео
VIDEO_ENCODER = os.getenv("VIDEO_ENCODER", "libx264").lower()
VIDEO_CRF = int(os.getenv("VIDEO_CRF", 16))
VIDEO_PRESET = os.getenv("VIDEO_PRESET", "slow")
VIDEO_NVENC_CQ = int(os.getenv("VIDEO_NVENC_CQ", 16))
VIDEO_PIX_FMT = os.getenv("VIDEO_PIX_FMT", "yuv420p")

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
