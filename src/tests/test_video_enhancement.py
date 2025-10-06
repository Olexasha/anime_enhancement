import asyncio
import os
from unittest.mock import patch

import pytest

from main import clean_up, main
from src.audio.audio_handling import AudioHandler
from src.config.comp_params import ComputerParams
from src.config.settings import (
    BATCH_VIDEO_PATH,
    FINAL_VIDEO,
    FRAMES_PER_BATCH,
    INPUT_BATCHES_DIR,
    ORIGINAL_VIDEO,
    TMP_VIDEO_PATH,
)
from src.frames.frames_helpers import extract_frames_to_batches
from src.frames.improve import delete_frames, upscale_batches
from src.video.video_handling import VideoHandler

pytestmark = pytest.mark.asyncio


class TestAudioHandler:
    @pytest.fixture
    def audio_handler(self):
        return AudioHandler(threads=4)

    async def test_extract_audio(self, audio_handler):
        with patch(
            "src.audio.audio_handling.AudioHandler.extract_audio"
        ) as mock_extract:
            await audio_handler.extract_audio()
            mock_extract.assert_called_once()

    def test_delete_audio_if_exists(self, audio_handler):
        with patch("os.path.exists", return_value=True), patch(
            "os.remove"
        ) as mock_remove:
            audio_handler.delete_audio_if_exists()
            mock_remove.assert_called_once()


class TestVideoHandler:
    @pytest.fixture
    def video_handler(self):
        return VideoHandler(fps=30)

    async def test_build_short_video(self, video_handler):
        with patch(
            "src.video.video_handling.VideoHandler.build_short_video"
        ) as mock_build:
            await video_handler.build_short_video(["batch_1", "batch_2"])
            mock_build.assert_called_once()

    async def test_build_final_video(self, video_handler):
        with patch(
            "src.video.video_handling.VideoHandler.build_final_video"
        ) as mock_build:
            result = await video_handler.build_final_video(3)
            mock_build.assert_called_once()
            assert result is not None


class TestFrameProcessing:
    def test_extract_frames_to_batches(self):
        with patch("os.makedirs") as mock_makedirs, patch(
            "cv2.VideoCapture"
        ) as mock_cap:
            mock_cap.return_value.get.return_value = 30
            mock_cap.return_value.read.return_value = (True, [1, 2, 3])
            extract_frames_to_batches(4)
            mock_makedirs.assert_called()

    async def test_upscale_batches(self):
        with patch("subprocess.Popen") as mock_popen:
            await upscale_batches(2, "4", "path/to/model", 1, 2)
            mock_popen.assert_called()


class TestComputerParams:
    def test_get_optimal_threads(self):
        comp = ComputerParams()
        ai_threads, process_threads = comp.get_optimal_threads()
        assert isinstance(ai_threads, str)
        assert isinstance(process_threads, int)
        assert process_threads > 0


class TestFileOperations:
    def test_delete_frames(self):
        with patch("os.path.exists", return_value=True), patch(
            "os.remove"
        ) as mock_remove:
            delete_frames(del_upscaled=True)
            mock_remove.assert_called()

    def test_clean_up(self):
        with patch(
            "src.audio.audio_handling.AudioHandler.delete_audio_if_exists"
        ) as mock_audio_delete, patch(
            "src.frames.upscale.delete_frames"
        ) as mock_frame_delete, patch(
            "glob.glob", return_value=["file1.mp4", "file2.mp4"]
        ), patch(
            "src.files.file_actions.delete_file"
        ) as mock_delete:
            audio_handler = AudioHandler(threads=4)
            asyncio.run(clean_up(audio_handler))
            mock_audio_delete.assert_called()
            mock_frame_delete.assert_called()
            assert mock_delete.call_count == 2


async def test_main_flow():
    with patch("src.config.comp_params.ComputerParams") as mock_comp, patch(
        "src.audio.audio_handling.AudioHandler"
    ) as mock_audio, patch(
        "src.frames.frames_helpers.extract_frames_to_batches"
    ) as mock_extract_frames, patch(
        "src.frames.upscale.upscale_batches"
    ) as mock_upscale, patch(
        "src.video.video_handling.VideoHandler"
    ) as mock_video:

        mock_comp.return_value.get_optimal_threads.return_value = ("4", 2)
        mock_comp.return_value.ai_realesrgan_path = "/path/to/model"

        await main()

        mock_audio.return_value.extract_audio.assert_called()
        mock_extract_frames.assert_called()
        mock_upscale.assert_called()
        mock_video.return_value.build_final_video.assert_called()
        mock_audio.return_value.insert_audio.assert_called()


@pytest.fixture
def cleanup_test_files():
    test_files = [
        os.path.join(BATCH_VIDEO_PATH, "test_batch.mp4"),
        os.path.join(INPUT_BATCHES_DIR, "batch_1"),
        os.path.join(TMP_VIDEO_PATH, "temp_video.mp4"),
        os.path.join(os.path.dirname(ORIGINAL_VIDEO), "test_video.mp4"),
        FINAL_VIDEO,
    ]

    yield

    for file in test_files:
        if os.path.exists(file):
            os.remove(file)
