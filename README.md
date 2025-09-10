# 🎨 Anime Enhancement

**Cross-platform Python tool for anime video upscaling with neural networks.**  
Enhances Full HD anime to 4K (or higher) using [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN), while preserving original audio and optimizing for performance via **batching and multithreading**.

<div align="center">
  <img src="https://img.shields.io/badge/Python-3.12+-orange?logo=python" alt="Python">
  <img src="https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-blue" alt="Platform">
  <img src="https://img.shields.io/badge/License-MIT-green" alt="License">
</div>

---

## 🔍 Overview

- 📹 **Automatic video enhancement**: Input → extract frames → upscale → merge video/audio
- 🔊 **Audio preservation**: Extracts, encodes, and merges audio back into final output
- ⚡ **Optimized batching**: Processes frames in parallel using threading/multiprocessing
- 🧠 **Anime-specialized upscaling model**: Uses pretrained Real-ESRGAN models (animevideo-v3)
- 🖥️ **Runs anywhere**: Includes platform-specific binaries (Windows, Linux, macOS)

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
3. Optional: Edit `.env` or config variables (e.g. batch size, scale factor)
4. Run enhancement:
```bash
python main.py
# or if inside poetry environment:
poetry run python main.py
```
---

## 📦 Example

Given: `data/input_video/naruto_war.mp4`

Output:
- Enhanced video at `data/output_video/naruto_war_enhanced.mp4`
- Audio preserved and synced

---

## 🧩 Features

- 🔁 Frame batching to reduce memory load
- 🧵 IO-bound multithreading for faster file ops
- ⚙️ Custom Real-ESRGAN execution per OS
- 🎛️ Configurable enhancement parameters (batch size, threads, model scale)
- 💾 Temporary and output directory management
- 📤 GUI and API interfaces under development

---

## ⚙️ Configuration

Main settings:
- `src/config/settings.py` — core parameters (video name, batch size, scale factor, etc.)
- `.env` — for optional overrides and system-level customization

---

## 🧠 Technology Stack

- Python 3.12+
- [ffmpeg](https://ffmpeg.org/) for audio/video processing
- `Real-ESRGAN` for frame enhancement (binaries included for 3 OSes)
- `threading`, `multiprocessing`, `asyncio` for parallelism
- `poetry` for dependency management

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

Want to improve anime upscaling tools? Help is welcome!

- Fork the repo and create PRs
- File issues or suggest features
- Test on your platform and report bugs

---

## 📜 License

MIT License — see [LICENSE](./LICENSE) file for full text.

---

## 🧠 Credits

- [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) by Xintao
- Inspired by anime remastering communities