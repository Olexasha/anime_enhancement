# 🎨 Anime Enhancement Suite

**Cross-platform Python toolchain for high-quality anime video restoration using neural networks.**  
Upscales, denoises, and interpolates anime videos — from old 360p/480p to sharp 4K+ — while preserving original audio and optimizing for performance via **batching, parallelism, and lightweight binaries**.

<div align="center">
  <img src="https://img.shields.io/badge/Python-3.12+-orange?logo=python" alt="Python">
  <img src="https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-blue" alt="Platform">
  <img src="https://img.shields.io/badge/License-MIT-green" alt="License">
  <img src="https://img.shields.io/badge/Upscale-Real--ESRGAN-purple" alt="Upscale">
  <img src="https://img.shields.io/badge/Denoise-Waifu2x-yellow" alt="Denoise">
  <img src="https://img.shields.io/badge/Interpolation-RIFE-red" alt="Interpolation">
</div>

---

## 🔍 What It Does

- 🎨 **Upscaling**: Enhances frames with [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN)
- 🧹 **Denoising**: Removes noise/artifacts with [waifu2x-ncnn-vulkan](https://github.com/nihui/waifu2x-ncnn-vulkan)
- 🎞️ **Interpolation**: Smooths motion & increases FPS with [RIFE-ncnn-vulkan](https://github.com/nihui/rife-ncnn-vulkan)
- 🔊 **Audio preservation**: Extracts, encodes, and syncs back audio tracks
- ⚡ **Optimized performance**: Frame batching + threading/multiprocessing
- 🖥️ **Cross-platform binaries included**: Works out-of-the-box on Windows, Linux, macOS

---


## 🚀 Quick Start

### ✅ Requirements

- Python **3.12+**
- `ffmpeg` installed and available in system `PATH`
- Basic dependencies managed by `poetry`

### 🧪 Installation

```bash
git clone https://github.com/Olexasha/anime_enhancement.git
cd anime_enhancement
poetry install
```

### ▶️ Usage
1. Place your video file in `data/input_video`;
2. Set video filename in `src/config/settings.py` under `ORIGINAL_VIDEO`
3. (Optional) Edit `.env`or settings (batch size, scale factor, FPS, denoise strength)
4. Run enhancement:
```bash
python main.py
# or if inside poetry environment:
poetry run python main.py
```
---

## 📦 Example Workflow

Input: `data/input_video/naruto_war.mp4`

Pipeline:
1. Extract audio
2. Extract frames
3. Apply **denoise** → **upscale** → **interpolation**
4. Merge video parts
5. Reattach synced audio

Output:
- `data/output_video/naruto_war_enhanced.mp4`

---

## 🧩 Features

- 🔁 Batch-based frame processing (low memory footprint)
- 🧵 IO-bound multithreading + CPU/GPU parallelism
- ⚙️ Custom Real-ESRGAN execution per OS
- 🎛️ Configurable stages: enable/disable upscale, denoise, interpolation
- ⚙️ Cross-OS binaries for ESRGAN, waifu2x, RIFE
- 💾 Automatic cleanup of temp files
- 📤 GUI and CLI (in progress)

---

## ⚙️ Configuration

Main settings:
- `src/config/settings.py` — core parameters (video name, batch size, scale factor, etc.)
- `.env` — for optional overrides and system-level customization

---

## 🧠 Tech Stack

- Python 3.12+
- [ffmpeg](https://ffmpeg.org/) — audio/video I/O
- [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN-ncnn-vulkan) — upscaling
- [Waifu2x](https://github.com/nihui/waifu2x-ncnn-vulkan) — denoising
- [RIFE](https://github.com/nihui/rife-ncnn-vulkan) — frame interpolation
- `threading`, `multiprocessing`, `asyncio` — parallel execution
- `poetry` — dependency management

---

## 🖼 Directory Structure

```
anime_enhancement/
├── data/
│   ├── input_video/              # Input video files
│   ├── output_video/             # Final enhanced videos
│   ├── audio/                    # Extracted audio files
│   ├── tmp_video/                # Temporary merging outputs
│   ├── default_frame_batches/    # Extracted frames
│   ├── upscaled_frame_batches/   # Enhanced frames
│   └── video_batches/            # Reconstructed video parts
├── src/
│   ├── audio/                    # Audio extraction/merging logic
│   ├── config/                   # Settings and constants
│   ├── files/                    # File management utilities
│   ├── frames/                   # Frame extraction and enhancement
│   ├── video/                    # Video processing logic
│   ├── utils/                    # Logging and Real-ESRGAN binaries
│   ├── interfaces/               # GUI and API (under development)
│   └── tests/                    # Pytest config (tests TBD)
├── pyproject.toml                # Poetry dependencies
├── main.py                       # Entry point
└── .env                          # Optional environment variables
```
---

## 📋 Future Roadmap

- [x] Add support for alternative upscaling models
- [x] Add denoising neural network (e.g. waifu2x)
- [x] Add motion interpolation (e.g. RIFE)
- [ ] Argparse CLI mode
- [ ] Complete GUI interface
- [ ] REST API for remote processing
- [ ] Upload to HuggingFace or PyPI

---

## 🧪 Testing

Planned to use `pytest`. Config file exists under `src/tests/pytest.ini`  
Run tests (once added) with:

```bash
poetry run pytest
```
---

## 💬 Contributing

Contributions welcome!

- Fork → PR
- File issues & feature requests
- Test across OSes & report bugs

---

## 📜 License

MIT License — see [LICENSE](./LICENSE) file for full text.

---

## 🧠 Credits

- [Waifu2x](https://github.com/nihui/waifu2x-ncnn-vulkan) by nihui
- [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) by Xintao
- [RIFE](https://github.com/nihui/rife-ncnn-vulkan) by nihui
- Inspired by anime remastering communities
