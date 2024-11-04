import os

from dotenv import load_dotenv

load_dotenv()
ROOT_DIR = os.getcwd()

# Пути к файлам
ORIGINAL_VIDEO = os.getenv("ORIGINAL_VIDEO", f"{ROOT_DIR}/data/input_video/bob_ru.mp4")
AUDIO_PATH = os.getenv("ORIGINAL_AUDIO", f"{ROOT_DIR}/data/audio")
TMP_FINAL_VIDEO = os.getenv(
    "TMP_FINAL_VIDEO", f"{ROOT_DIR}/data/output_video/tmp_final_video.mp4"
)
FINAL_VIDEO = os.getenv("FINAL_VIDEO", f"{ROOT_DIR}/data/output_video/final_video.mp4")
BATCH_VIDEO_PATH = os.getenv("BATCH_VIDEO_PATH", f"{ROOT_DIR}/data/video_batches")
INPUT_BATCHES_DIR = os.getenv(
    "INPUT_BATCHES_DIR", f"{ROOT_DIR}/data/default_frame_batches"
)
OUTPUT_BATCHES_DIR = os.getenv(
    "OUTPUT_BATCHES_DIR", f"{ROOT_DIR}/data/upscaled_frame_batches"
)

# Файловые параметры апскейлера
RESOLUTION = os.getenv("RESOLUTION", "4K")
START_BATCH_TO_UPSCALE = int(os.getenv("START_BATCH_TO_UPSCALE", 1))
END_BATCH_TO_UPSCALE = int(os.getenv("END_BATCH_TO_UPSCALE", 0))
STEP_PER_BATCH = int(os.getenv("STEP_PER_BATCH", 6))
FRAMES_PER_BATCH = int(os.getenv("FRAMES_PER_BATCH", 1000))

MERGE_ALL_BATCHES_TO_VIDEO = bool(os.getenv("MERGE_ALL_BATCHES_TO_VIDEO", True))
ALLOWED_THREADS = int(os.getenv("ALLOWED_THREADS", 6))

# Настройка апскейла
UPSCALE_MODEL_NAME = os.getenv("UPSCALE_MODEL_NAME", f"{ROOT_DIR}/src/utils/realesrgan/models/realesr-animevideov3")
UPSCALE_FACTOR = int(os.getenv("UPSCALE_FACTOR", 2))
OUTPUT_IMAGE_FORMAT = os.getenv("OUTPUT_IMAGE_FORMAT", "jpg")
