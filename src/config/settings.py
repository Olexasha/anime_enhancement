import os

from dotenv import load_dotenv

load_dotenv()
ROOT_DIR = os.getcwd()

# Пути к файлам
ORIGINAL_VIDEO = os.path.join(ROOT_DIR, "data", "input_video", "naruto_test.mp4")
AUDIO_PATH = os.path.join(ROOT_DIR, "data", "audio")
TMP_VIDEO = os.path.join(ROOT_DIR, "data", "tmp_video", "final_merge.mp4")
FINAL_VIDEO = os.path.join(ROOT_DIR, "data", "output_video", "final_video.mp4")
BATCH_VIDEO_PATH = os.path.join(ROOT_DIR, "data", "video_batches")
INPUT_BATCHES_DIR = os.path.join(ROOT_DIR, "data", "default_frame_batches")
OUTPUT_BATCHES_DIR = os.path.join(ROOT_DIR, "data", "upscaled_frame_batches")

# Файловые параметры апскейлера
RESOLUTION = os.getenv("RESOLUTION", "4K")
START_BATCH_TO_UPSCALE = int(os.getenv("START_BATCH_TO_UPSCALE", 1))
END_BATCH_TO_UPSCALE = int(os.getenv("END_BATCH_TO_UPSCALE", 0))
STEP_PER_BATCH = int(os.getenv("STEP_PER_BATCH", 6))
FRAMES_PER_BATCH = int(os.getenv("FRAMES_PER_BATCH", 1000))
ALLOWED_THREADS = int(os.getenv("ALLOWED_THREADS", 6))

# Настройка апскейла
MODEL_DIR = os.path.join(ROOT_DIR, "src", "utils", "realesrgan", "models")
MODEL_NAME = os.getenv("MODEL_NAME", "realesr-animevideov3")
_OS = os.getenv("_OS", "linux")
REALESRGAN_SCRIPT = os.path.join(
    ROOT_DIR, "src", "utils", "realesrgan", f"realesrgan-{_OS}", f"realesrgan-ncnn-vulkan{".exe" if _OS == 'win' else ""}"
)
UPSCALE_FACTOR = int(os.getenv("UPSCALE_FACTOR", 2))
OUTPUT_IMAGE_FORMAT = os.getenv("OUTPUT_IMAGE_FORMAT", "jpg")
