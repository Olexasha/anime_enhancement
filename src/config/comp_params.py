import os
import platform
import re
import subprocess as sp
from functools import cached_property, lru_cache
from pathlib import Path
from typing import Optional, Tuple

import psutil

from src.config.settings import ROOT_DIR
from src.utils.logger import logger


class ComputerParams:
    """Класс для сбора параметров системы и расчета оптимальных настроек выполнения задач.

        Собирает информацию об аппаратных характеристиках системы и предоставляет методы
        для определения оптимальных параметров выполнения ресурсоемких задач.

        Атрибуты:
            cpu_name (str): Название процессора
            cpu_threads (int): Общее количество потоков процессора
            safe_cpu_threads (int): Безопасное количество используемых потоков (80% от общего)
            ram_total (float): Общий объем оперативной памяти в ГБ
            ssd_speed (float): Примерная скорость работы накопителя в MB/s
        """

    MIN_RAM_GB = 4
    MIN_CPU_THREADS = 2
    MIN_GPU_MEMORY = 2048  # мин рекомендуемая память GPU в MB
    MIN_SSD_SPEED = 500    # мин рекомендуемая скорость SSD в MB/s

    def __init__(self):
        try:
            self.cpu_name = platform.processor()
            self.cpu_threads = self._get_cpu_threads()
            self.safe_cpu_threads = self._calculate_safe_cpu_threads()
            self.ram_total = self._get_ram_total()
            self.ssd_speed = self._estimate_ssd_speed()
            self.__validate_resources()
        except Exception as e:
            logger.error(f"Ошибка инициализации системы: {str(e)}")
            raise

    @lru_cache(maxsize=1)
    def _get_cpu_threads(self) -> int:
        """Получение количества доступных потоков процессора.
        Использует несколько методов определения с резервными вариантами.
        :return: Количество логических процессоров (не менее 1)
        """
        try:
            cpu_count = os.cpu_count()
            if cpu_count is None:
                cpu_count = psutil.cpu_count(logical=True)
            return cpu_count or 1
        except Exception as e:
            logger.warning(f"Ошибка получения количества потоков CPU: {str(e)}")
            return 1

    @lru_cache(maxsize=1)
    def _get_ram_total(self) -> float:
        """Получение общего объема оперативной памяти в ГБ.
        :return: Объем RAM в гигабайтах с округлением до 2 знаков
        """
        try:
            mem = psutil.virtual_memory()
            return round(mem.total / (1024**3), 2)
        except Exception as e:
            logger.warning(f"Error getting RAM info: {str(e)}")
            return 4.0  # консервативное значение по умолчанию

    @cached_property
    def os(self) -> str:
        """Определение типа операционной системы.
        :return: Идентификатор ОС ('win', 'linux' или 'macos')
        :rtype: str
        :raises ValueError: Если ОС не поддерживается
        """
        try:
            system = platform.system()
            match system:
                case "Windows":
                    return "win"
                case "Linux":
                    return "linux"
                case "Darwin":
                    return "macos"
                case _:
                    raise ValueError(f"Неподдерживаемая ОС: {system}")
        except Exception as e:
            logger.error(f"Ошибка определения ОС: {str(e)}")
            raise

    @cached_property
    def gpu_name(self) -> str:
        """Получение названия GPU с обработкой ошибок.
        :return: Название GPU или сообщение об ошибке
        :rtype: str
        """
        try:
            if not self._is_nvidia_smi_installed():
                return "NVIDIA GPU не обнаружен или nvidia-smi не установле"
            
            gpu_info = self._run_subprocess(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"]
            )
            return gpu_info.strip() if gpu_info else "GPU не обнаружен"
        except Exception as e:
            logger.warning(f"Ошибка получения информации о GPU: {str(e)}")
            return "Ошибка определения GPU"

    @cached_property
    def gpu_memory(self) -> int:
        """Получение объема памяти GPU в MB.
        :return: Объем видеопамяти в MB (0 если не удалось определить)
        :rtype: int
        """
        try:
            if not self._is_nvidia_smi_installed():
                return 0
            
            raw = self._run_subprocess(
                ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader"]
            )
            if raw:
                return int(raw.strip().split()[0])  # память в MiB
            return 0
        except Exception as e:
            logger.warning(f"Ошибка получения объема памяти GPU: {str(e)}")
            return 0

    @cached_property
    def ai_realesrgan_path(self) -> str:
        """Получает AI RealESRGAN-ncnn-vulkan путь к исполняемому файлу"""
        try:
            executable = "realesrgan-ncnn-vulkan" + (".exe" if self.os == "win" else "")
            path = os.path.join(
                ROOT_DIR, "src", "utils", "realesrgan", f"realesrgan-{self.os}", executable
            )
            if not Path(path).exists():
                logger.warning(f"AI executable not found at {path}")
                raise FileNotFoundError(f"AI executable not found at {path}")
            return path
        except Exception as e:
            logger.error(f"Error getting AI executable path: {str(e)}")
            raise

    @staticmethod
    def _is_nvidia_smi_installed() -> bool:
        """Check if nvidia-smi is available"""
        try:
            sp.run(["nvidia-smi"], capture_output=True, check=True)
            return True
        except:
            return False

    def get_optimal_threads(self) -> Tuple[str, int]:
        """
        Рассчитывает оптимальные параметры для -j load:proc:save и количество процессов/тредов
        """
        try:
            processes = self._calculate_processing_threads()
            save_threads = self._calculate_save_threads()
            proc_threads = self._calculate_proc_threads(processes)
            load_threads = max(1, save_threads - 1)

            # подбираем load:proc:save
            j_params = f"{load_threads}:{proc_threads}:{save_threads}"
            logger.info(f"Optimal thread configuration: {j_params} with {processes} processes")
            return j_params, processes
        except Exception as e:
            logger.error(f"Error calculating optimal threads: {str(e)}")
            raise

    def _calculate_processing_threads(self) -> int:
        """Считает количество безопасных процессов для запуска нейронок параллельно"""
        try:
            if self.safe_cpu_threads >= 12 and self.gpu_memory >= 4096:
                return 6
            return min(4, self.safe_cpu_threads // 2)
        except Exception as e:
            logger.warning(f"Error calculating processing threads: {str(e)}")
            return 2  # дефолт

    def _calculate_safe_cpu_threads(self) -> int:
        """Calculate safe CPU threads usage"""
        try:
            # Use 80% of available threads, but not less than 2
            return max(2, round(self.cpu_threads * 0.8))
        except Exception as e:
            logger.warning(f"Error calculating safe CPU threads: {str(e)}")
            return 2

    def _estimate_ssd_speed(self) -> float:
        """Грубая оценка скорости диска (MB/s)."""
        try:
            if self.os == "win":
                # консервоативная оценка для винды
                return 2000

            # для Linux/MacOS используем относительно хорошую оценку скорости
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
                speed = float(match.group(1)) if match else 500
                logger.info(f"SSD speed estimated at {speed} MB/s")
                return speed
            except Exception as e:
                logger.warning(f"SSD speed test failed: {str(e)}")
                return 500  # дефолт
            finally:
                Path(test_file).unlink()

        except Exception as e:
            logger.warning(f"Error estimating SSD speed: {str(e)}")
            return 500

    def _calculate_save_threads(self) -> int:
        """Потоки для загрузки (зависит от SSD)"""
        try:
            if self.ssd_speed >= 2000:  # NVMe
                return 2
            return 2 if self.ssd_speed >= 500 else 1  # SATA SSD или HDD
        except Exception as e:
            logger.warning(f"Error calculating save threads: {str(e)}")
            return 1

    def _calculate_proc_threads(self, processes: int) -> int:
        """Потоки для обработки с учётом количества процессов"""
        try:
            safe_threads = max(2, self.safe_cpu_threads // max(1, processes) - 1)
            return min(8, safe_threads)  # не больше 8 даже для мощных CPU
        except Exception as e:
            logger.warning(f"Error calculating proc threads: {str(e)}")
            return 2

    @staticmethod
    def _run_subprocess(cmd: list) -> Optional[str]:
        """Запуск подпроцесса с обработкой ошибок"""
        try:
            result = sp.run(cmd, capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except (sp.CalledProcessError, FileNotFoundError) as e:
            logger.error(f"Subprocess error: {str(e)}")
            return None

    def __validate_resources(self) -> None:
        """Проверка соответствия системы минимальным требованиям."""
        try:
            if self.ram_total < self.MIN_RAM_GB:
                logger.warning(
                    f"В системе только {self.ram_total}GB RAM. "
                    f"Рекомендуемый минимум: {self.MIN_RAM_GB}GB"
                )

            if self.cpu_threads < self.MIN_CPU_THREADS:
                logger.warning(
                    f"В системе только {self.cpu_threads} потоков CPU. "
                    f"Рекомендуемый минимум: {self.MIN_CPU_THREADS}"
                )

            if self.gpu_memory < self.MIN_GPU_MEMORY:
                logger.warning(
                    f"GPU имеет только {self.gpu_memory}MB памяти. "
                    f"Рекомендуемый минимум: {self.MIN_GPU_MEMORY}MB"
                )

            if self.ssd_speed < self.MIN_SSD_SPEED:
                logger.warning(
                    f"Скорость накопителя: {self.ssd_speed}MB/s. "
                    f"Рекомендуемый минимум: {self.MIN_SSD_SPEED}MB/s"
                )

        except Exception as e:
            logger.error(f"Ошибка проверки ресурсов системы: {str(e)}")
            raise

    def __str__(self) -> str:
        try:
            return (
                f"ОС: {self.os}\n"
                f"Процессор: {self.cpu_name} ({self.cpu_threads} потоков, безопасно: {self.safe_cpu_threads})\n"
                f"Видеокарта: {self.gpu_name} ({self.gpu_memory} MB)\n"
                f"Оперативная память: {self.ram_total} GB\n"
                f"Скорость SSD: {self.ssd_speed} MB/s\n"
            )
        except Exception as e:
            logger.error(f"Ошибка генерации информации о системе: {str(e)}")
            return "Информация о системе недоступна"

    __repr__ = __str__
