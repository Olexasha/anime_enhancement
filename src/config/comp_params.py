import os
import platform
import re
import subprocess as sp
from functools import cached_property
from typing import Optional, Tuple

import psutil

from src.config.settings import ROOT_DIR
from src.files.file_actions import delete_file


class ComputerParams:
    def __init__(self):
        self.cpu_name = platform.processor()
        self.cpu_threads = os.cpu_count() or 1
        self.safe_cpu_threads = round(
            self.cpu_threads * 0.8
        )  # используем 80% от доступных потоков
        self.ram_total = round(psutil.virtual_memory().total / (1024**3), 2)  # in GB
        self.ssd_speed = self._estimate_ssd_speed()  # in MB/s
        self.__validate_resources()  # проверяем минимальные требования

    @cached_property
    def os(self) -> str:
        match platform.system():
            case "Windows":
                return "win"
            case "Linux":
                return "linux"
            case "Darwin":
                return "macos"
            case _:
                raise ValueError("Неподдерживаемая операционная система")

    @cached_property
    def gpu_name(self) -> str:
        return (
            self._run_subprocess(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"]
            )
            or "Нет доступных GPU или nvidia-smi не установлен"
        )

    @cached_property
    def gpu_memory(self) -> str | int:
        raw = self._run_subprocess(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader"]
        )
        if raw:
            return int(raw.split()[0])  # в MB
        return "Нет информации о GPU"

    @cached_property
    def ai_realesrgan_path(self) -> str:
        executable = "realesrgan-ncnn-vulkan" + (".exe" if self.os == "win" else "")
        return os.path.join(
            ROOT_DIR, "src", "utils", "realesrgan", f"realesrgan-{self.os}", executable
        )

    def get_optimal_threads(self) -> Tuple[str, int]:
        """
        Рассчитывает оптимальные параметры для -j load:proc:save и количество процессов/тредов.
        """
        processes = self._calculate_processing_threads()
        save_threads = self._calculate_save_threads()
        proc_threads = self._calculate_proc_threads(processes)
        load_threads = max(1, save_threads - 1)

        # подбираем load:proc:save
        j_params = f"{load_threads}:{proc_threads}:{save_threads}"
        return j_params, processes

    def _calculate_processing_threads(self) -> int:
        """Считает количество безопасных процессов для запуска нейронок параллельно."""
        if self.safe_cpu_threads >= 12:
            return 6
        return min(4, self.safe_cpu_threads // 2)

    def _estimate_ssd_speed(self) -> float:
        """Грубая оценка скорости диска (MB/s)."""
        if self.os == "win":
            return 2000  # для Windows сложно измерить без сторонних утилит

        # Linux или MacOS: используем dd для теста
        test_file = "/tmp/speedtest.tmp"
        cmd = [
            "dd",
            "if=/dev/zero",
            f"of={test_file}",
            "bs=1M",
            "count=1024",
            "conv=fdatasync",
        ]

        try:
            result = sp.run(
                cmd, stderr=sp.PIPE, stdout=sp.DEVNULL, text=True, check=True
            )
            match = re.search(r"(\d+(?:\.\d+)?)\s+MB/s", result.stderr)
            return float(match.group(1)) if match else 500
        except (sp.CalledProcessError, FileNotFoundError):
            return 500  # консервативная оценка по умолчанию
        finally:
            delete_file(test_file)

    def _calculate_save_threads(self) -> int:
        """Потоки для загрузки (зависит от SSD)."""
        if self.ssd_speed >= 2000:  # NVMe
            return 2
        return 2 if self.ssd_speed >= 500 else 1  # SATA SSD или HDD

    def _calculate_proc_threads(self, processes: int) -> int:
        """Потоки для обработки с учётом количества процессов."""
        safe_threads = max(2, self.safe_cpu_threads // max(1, processes) - 1)
        return min(8, safe_threads)  # Не больше 8 даже для мощных CPU

    @staticmethod
    def _run_subprocess(cmd: list) -> Optional[str]:
        """Запускает команду в subprocess и возвращает вывод или None в случае ошибки."""
        try:
            result = sp.run(cmd, capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except (sp.CalledProcessError, FileNotFoundError):
            return None

    def __validate_resources(self):
        """Проверяет минимальные требования к системе."""
        if self.gpu_memory < 2048:
            raise RuntimeError("Недостаточно VRAM (требуется минимум 2 ГБ)")
        if self.ram_total < 8:
            raise RuntimeError("Недостаточно RAM (требуется минимум 8 ГБ)")

    def __str__(self) -> str:
        return (
            f"OS: {self.os}\n"
            f"CPU: {self.cpu_name} ({self.cpu_threads} threads, safe: {self.safe_cpu_threads})\n"
            f"GPU: {self.gpu_name} ({self.gpu_memory} MB)\n"
            f"RAM: {self.ram_total} GB\n"
            f"SSD Speed: {self.ssd_speed} MB/s\n"
        )

    __repr__ = __str__
