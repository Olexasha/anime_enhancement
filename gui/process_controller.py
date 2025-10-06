"""
Контроллер процессов для запуска main.py и стриминга логов.

Обеспечивает запуск, мониторинг и остановку процесса обработки видео
с передачей логов в реальном времени в GUI.
"""

import os
import signal
import sys
import time
from pathlib import Path
from typing import Optional, Dict, Any
from PySide6.QtCore import QObject, QProcess, Signal

import logging


class ProcessController(QObject):
    """Контроллер для управления процессом обработки видео."""
    
    # Сигналы для уведомления о состоянии процесса
    process_started = Signal()
    process_finished = Signal(int)  # код завершения
    process_error = Signal(str)  # сообщение об ошибке
    log_output = Signal(str, str)  # (уровень, сообщение)
    progress_updated = Signal(int)  # процент выполнения
    
    def __init__(self, project_root: Path, config_manager):
        super().__init__()
        self.project_root = project_root
        self.config_manager = config_manager
        self.process: Optional[QProcess] = None
        self.is_running = False
        self.start_time: Optional[float] = None
        
        # Настраиваем логирование
        self.logger = logging.getLogger(__name__)
    
    def start_process(self, config: Dict[str, Any]) -> bool:
        """Запускает процесс обработки видео."""
        try:
            if self.is_running:
                self.log_output.emit("WARNING", "Процесс уже запущен")
                return False
            
            # Проверяем входной файл
            input_video = config.get("ORIGINAL_VIDEO", "")
            if not input_video or not Path(input_video).exists():
                self.process_error.emit(f"Входной файл не найден: {input_video}")
                return False
            
            # Проверяем свободное место на диске
            if not self._check_disk_space():
                return False
            
            # Создаем процесс
            self.process = QProcess()
            self.process.readyReadStandardOutput.connect(self._on_stdout)
            self.process.readyReadStandardError.connect(self._on_stderr)
            self.process.finished.connect(self._on_finished)
            self.process.errorOccurred.connect(self._on_error)
            
            # Настраиваем переменные окружения
            env = os.environ.copy()
            env["PYTHONPATH"] = str(self.project_root)
            
            # Если есть переопределения конфигурации, передаем их
            if self.config_manager.override_json_path.exists():
                env["GUI_SETTINGS"] = str(self.config_manager.override_json_path)
            
            self.process.setProcessEnvironment(env)
            
            # Запускаем main.py
            main_py_path = self.project_root / "main.py"
            self.process.start(sys.executable, [str(main_py_path)])
            
            if not self.process.waitForStarted(5000):  # 5 секунд на запуск
                self.process_error.emit("Не удалось запустить процесс")
                return False
            
            self.is_running = True
            self.start_time = time.time()
            self.process_started.emit()
            self.log_output.emit("INFO", "Процесс обработки видео запущен")
            
            return True
            
        except Exception as e:
            self.process_error.emit(f"Ошибка запуска процесса: {str(e)}")
            return False
    
    def stop_process(self) -> bool:
        """Останавливает процесс обработки видео."""
        try:
            if not self.is_running or not self.process:
                self.log_output.emit("WARNING", "Процесс не запущен")
                return False
            
            self.log_output.emit("INFO", "Остановка процесса...")
            
            # Сначала пытаемся корректно завершить процесс
            self.process.terminate()
            
            # Ждем завершения до 10 секунд
            if not self.process.waitForFinished(10000):
                # Если не завершился, принудительно убиваем
                self.log_output.emit("WARNING", "Принудительное завершение процесса")
                self.process.kill()
                self.process.waitForFinished(5000)
            
            self.is_running = False
            self.log_output.emit("INFO", "Процесс остановлен")
            
            return True
            
        except Exception as e:
            self.process_error.emit(f"Ошибка остановки процесса: {str(e)}")
            return False
    
    def pause_process(self) -> bool:
        """Приостанавливает процесс (если поддерживается)."""
        try:
            if not self.is_running or not self.process:
                return False
            
            # На Windows используем CTRL_BREAK_EVENT
            if sys.platform == "win32":
                self.process.kill()  # В Qt нет прямого способа отправить CTRL_BREAK
            else:
                os.kill(self.process.processId(), signal.SIGSTOP)
            
            self.log_output.emit("INFO", "Процесс приостановлен")
            return True
            
        except Exception as e:
            self.process_error.emit(f"Ошибка приостановки процесса: {str(e)}")
            return False
    
    def resume_process(self) -> bool:
        """Возобновляет приостановленный процесс."""
        try:
            if not self.process:
                return False
            
            if sys.platform != "win32":
                os.kill(self.process.processId(), signal.SIGCONT)
                self.log_output.emit("INFO", "Процесс возобновлен")
                return True
            
            return False
            
        except Exception as e:
            self.process_error.emit(f"Ошибка возобновления процесса: {str(e)}")
            return False
    
    def get_process_info(self) -> Dict[str, Any]:
        """Возвращает информацию о текущем процессе."""
        if not self.process or not self.is_running:
            return {}
        
        return {
            "pid": self.process.processId(),
            "running": self.is_running,
            "start_time": self.start_time,
            "elapsed_time": time.time() - self.start_time if self.start_time else 0,
        }
    
    def _on_stdout(self):
        """Обработчик вывода stdout."""
        if not self.process:
            return
        
        data = self.process.readAllStandardOutput().data().decode('utf-8', errors='ignore')
        for line in data.strip().split('\n'):
            if line.strip():
                self._process_log_line(line.strip())
    
    def _on_stderr(self):
        """Обработчик вывода stderr."""
        if not self.process:
            return
        
        data = self.process.readAllStandardError().data().decode('utf-8', errors='ignore')
        for line in data.strip().split('\n'):
            if line.strip():
                self._process_log_line(line.strip(), is_error=True)
    
    def _process_log_line(self, line: str, is_error: bool = False):
        """Обрабатывает строку лога и определяет уровень."""
        # Определяем уровень логирования по содержимому
        if is_error or "ERROR" in line.upper() or "CRITICAL" in line.upper():
            level = "ERROR"
        elif "WARNING" in line.upper() or "WARN" in line.upper():
            level = "WARNING"
        elif "SUCCESS" in line.upper() or "✅" in line:
            level = "SUCCESS"
        elif "INFO" in line.upper() or "🎯" in line:
            level = "INFO"
        else:
            level = "DEBUG"
        
        # Пытаемся извлечь процент выполнения
        self._extract_progress(line)
        
        self.log_output.emit(level, line)
    
    def _extract_progress(self, line: str):
        """Извлекает процент выполнения из строки лога."""
        # Простая эвристика для определения прогресса
        # В реальном проекте нужно адаптировать под конкретные сообщения main.py
        if "батч" in line.lower() and "из" in line.lower():
            # Пытаемся найти числа в строке типа "батч 5 из 20"
            import re
            numbers = re.findall(r'\d+', line)
            if len(numbers) >= 2:
                try:
                    current = int(numbers[0])
                    total = int(numbers[1])
                    if total > 0:
                        progress = int((current / total) * 100)
                        self.progress_updated.emit(progress)
                except (ValueError, ZeroDivisionError):
                    pass
    
    def _on_finished(self, exit_code: int):
        """Обработчик завершения процесса."""
        self.is_running = False
        self.process_finished.emit(exit_code)
        
        if exit_code == 0:
            self.log_output.emit("SUCCESS", "Процесс успешно завершен")
        else:
            self.log_output.emit("ERROR", f"Процесс завершен с кодом ошибки: {exit_code}")
    
    def _on_error(self, error):
        """Обработчик ошибок процесса."""
        self.is_running = False
        error_msg = f"Ошибка процесса: {error}"
        self.process_error.emit(error_msg)
        self.log_output.emit("ERROR", error_msg)
    
    def _check_disk_space(self) -> bool:
        """Проверяет свободное место на диске."""
        try:
            import shutil
            free_space = shutil.disk_usage(self.project_root).free
            free_gb = free_space / (1024**3)
            
            # Требуем минимум 10 ГБ свободного места
            min_free_gb = 10
            if free_gb < min_free_gb:
                self.process_error.emit(
                    f"Недостаточно свободного места на диске. "
                    f"Доступно: {free_gb:.1f} ГБ, требуется: {min_free_gb} ГБ"
                )
                return False
            
            self.log_output.emit("INFO", f"Свободное место на диске: {free_gb:.1f} ГБ")
            return True
            
        except Exception as e:
            self.log_output.emit("WARNING", f"Не удалось проверить свободное место: {str(e)}")
            return True  # Продолжаем, если не удалось проверить
