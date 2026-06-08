Linux portable-сборка
=======================

1. Распакуйте архив AnimeEnhancement-Linux.tar.gz.
2. Запустите ./AnimeEnhancement из распакованной папки.
3. Если FFmpeg не включен в сборку, установите его через пакетный менеджер, например: sudo apt install ffmpeg.
4. RealESRGAN/waifu2x/RIFE требуют Linux binaries в src/utils/*/*-linux и рабочий Vulkan-драйвер.

Это portable-архив, он не выполняет системную установку и не меняет глобальный PATH.
