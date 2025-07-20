import os

from dotenv import load_dotenv

load_dotenv()
ROOT_DIR = os.getcwd()

# Пути к файлам
ORIGINAL_VIDEO = os.path.join(ROOT_DIR, "data", "input_video", "naruto_test2.mkv")
AUDIO_PATH = os.path.join(ROOT_DIR, "data", "audio")
TMP_VIDEO_PATH = os.path.join(ROOT_DIR, "data", "tmp_video")
FINAL_VIDEO = os.path.join(ROOT_DIR, "data", "output_video", "final_video.mp4")
BATCH_VIDEO_PATH = os.path.join(ROOT_DIR, "data", "video_batches")
INPUT_BATCHES_DIR = os.path.join(ROOT_DIR, "data", "default_frame_batches")
OUTPUT_BATCHES_DIR = os.path.join(ROOT_DIR, "data", "upscaled_frame_batches")

# Файловые параметры апскейлера
RESOLUTION = os.getenv("RESOLUTION", "4K")
START_BATCH_TO_UPSCALE = int(os.getenv("START_BATCH_TO_UPSCALE", 1))
END_BATCH_TO_UPSCALE = int(os.getenv("END_BATCH_TO_UPSCALE", 0))
FRAMES_PER_BATCH = int(os.getenv("FRAMES_PER_BATCH", 1000))

# Настройка апскейла
MODEL_DIR = os.path.join(ROOT_DIR, "src", "utils", "realesrgan", "models")
MODEL_NAME = os.getenv("MODEL_NAME", "realesr-animevideov3")
UPSCALE_FACTOR = int(os.getenv("UPSCALE_FACTOR", 2))
OUTPUT_IMAGE_FORMAT = os.getenv("OUTPUT_IMAGE_FORMAT", "jpg")
