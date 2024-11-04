#!/bin/bash

# Проверка на наличие аргументов
if [ "$#" -ne 2 ]; then
    echo "Использование: $0 <начальный_номер_батча> <конечный_номер_батча>"
    exit 1
fi

# Параметры и пути
BATCHES_DIR="/home/uzver_pro/Video_Montage/batches"
OUTPUT_FRAMES_DIR="/media/uzver_pro/7d3a855c-208a-4e34-9b13-1f70d2e178e5/anime_upscaling/batches"
START_BATCH=$1  # Начальный номер батча
END_BATCH=$2    # Конечный номер батча

# Создание директорий для указанных батчей
for batch_num in $(seq "$START_BATCH" "$END_BATCH"); do
    mkdir -p "$OUTPUT_FRAMES_DIR/batch_$batch_num"
done

# Функция для улучшения фреймов в батче
upscale_batch() {
    local batch_num=$1
    ./src/utils/realesrgan/realesrgan-linux/realesrgan-ncnn-vulkan -i "$BATCHES_DIR/batch_$batch_num" -o "$OUTPUT_FRAMES_DIR/batch_$batch_num" -n realesr-animevideov3 -s 2 -f jpg 2>&1 | tee /dev/stdout
}

# Запуск обработки батчей в параллельных процессах
for batch_num in $(seq "$START_BATCH" "$END_BATCH"); do
    upscale_batch $batch_num &
done

# Ожидание завершения всех процессов
wait

echo "Обработка всех батчей завершена."
