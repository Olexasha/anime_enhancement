"""
Unit тесты для ProcessController.

Тестирует управление процессами и стриминг логов.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, Mock

import sys

# Добавляем корневую директорию проекта в путь
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication

# Создаем QApplication для тестов
app = QApplication.instance()
if app is None:
    app = QApplication([])

from gui.process_controller import ProcessController
from gui.config import ConfigManager


class TestProcessController(unittest.TestCase):
    """Тесты для ProcessController."""
    
    def setUp(self):
        """Настройка тестового окружения."""
        self.temp_dir = tempfile.mkdtemp()
        self.project_root = Path(self.temp_dir)
        
        # Создаем тестовую структуру
        (self.project_root / "src" / "config").mkdir(parents=True)
        (self.project_root / "data" / "input_video").mkdir(parents=True)
        
        # Создаем тестовый main.py
        main_py_path = self.project_root / "main.py"
        main_py_path.write_text("""
import time
import sys

def main():
    print("Test process started")
    print("Processing video...")
    for i in range(5):
        print(f"Progress: {i * 20}%")
        time.sleep(0.1)
    print("Test process completed")
    return 0

if __name__ == "__main__":
    sys.exit(main())
""")
        
        # Создаем тестовый видеофайл
        test_video = self.project_root / "data" / "input_video" / "test.mp4"
        test_video.write_text("fake video content")
        
        # Создаем конфигурацию
        self.config_manager = ConfigManager(self.project_root)
        self.process_controller = ProcessController(self.project_root, self.config_manager)
        
        # Подключаем сигналы для тестирования
        self.log_messages = []
        self.process_controller.log_output.connect(self._on_log_output)
    
    def tearDown(self):
        """Очистка после тестов."""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def _on_log_output(self, level, message):
        """Обработчик сигнала логов для тестирования."""
        self.log_messages.append((level, message))
    
    def test_initialization(self):
        """Тест инициализации ProcessController."""
        self.assertFalse(self.process_controller.is_running)
        self.assertIsNone(self.process_controller.process)
        self.assertIsNone(self.process_controller.start_time)
    
    def test_check_disk_space(self):
        """Тест проверки свободного места на диске."""
        # Мокаем shutil.disk_usage для тестирования
        with patch('gui.process_controller.shutil.disk_usage') as mock_disk_usage:
            # Тест с достаточным местом
            mock_disk_usage.return_value.free = 20 * 1024**3  # 20 GB
            result = self.process_controller._check_disk_space()
            self.assertTrue(result)
            
            # Тест с недостаточным местом
            mock_disk_usage.return_value.free = 5 * 1024**3  # 5 GB
            result = self.process_controller._check_disk_space()
            self.assertFalse(result)
    
    def test_extract_progress(self):
        """Тест извлечения прогресса из строки лога."""
        # Тест с корректной строкой прогресса
        self.process_controller._extract_progress("батч 5 из 20")
        # Проверяем, что сигнал progress_updated был отправлен
        # (в реальном тесте нужно мокать сигнал)
        
        # Тест с некорректной строкой
        self.process_controller._extract_progress("обычное сообщение")
        # Не должно быть ошибок
    
    def test_process_log_line(self):
        """Тест обработки строки лога."""
        # Очищаем предыдущие сообщения
        self.log_messages.clear()
        
        # Тест ERROR уровня
        self.process_controller._process_log_line("ERROR: Something went wrong")
        self.assertEqual(len(self.log_messages), 1)
        self.assertEqual(self.log_messages[0][0], "ERROR")
        
        # Тест WARNING уровня
        self.log_messages.clear()
        self.process_controller._process_log_line("WARNING: This is a warning")
        self.assertEqual(len(self.log_messages), 1)
        self.assertEqual(self.log_messages[0][0], "WARNING")
        
        # Тест SUCCESS уровня
        self.log_messages.clear()
        self.process_controller._process_log_line("SUCCESS: Operation completed")
        self.assertEqual(len(self.log_messages), 1)
        self.assertEqual(self.log_messages[0][0], "SUCCESS")
        
        # Тест INFO уровня
        self.log_messages.clear()
        self.process_controller._process_log_line("INFO: Processing started")
        self.assertEqual(len(self.log_messages), 1)
        self.assertEqual(self.log_messages[0][0], "INFO")
    
    @patch('gui.process_controller.QProcess')
    def test_start_process_success(self, mock_qprocess_class):
        """Тест успешного запуска процесса."""
        # Мокаем QProcess
        mock_process = Mock()
        mock_qprocess_class.return_value = mock_process
        mock_process.waitForStarted.return_value = True
        
        # Создаем тестовую конфигурацию
        config = {
            "ORIGINAL_VIDEO": str(self.project_root / "data" / "input_video" / "test.mp4")
        }
        
        # Запускаем процесс
        result = self.process_controller.start_process(config)
        
        self.assertTrue(result)
        self.assertTrue(self.process_controller.is_running)
        self.assertIsNotNone(self.process_controller.start_time)
        mock_process.start.assert_called_once()
    
    @patch('gui.process_controller.QProcess')
    def test_start_process_file_not_found(self, mock_qprocess_class):
        """Тест запуска процесса с несуществующим файлом."""
        # Создаем конфигурацию с несуществующим файлом
        config = {
            "ORIGINAL_VIDEO": "nonexistent_video.mp4"
        }
        
        # Запускаем процесс
        result = self.process_controller.start_process(config)
        
        self.assertFalse(result)
        self.assertFalse(self.process_controller.is_running)
    
    @patch('gui.process_controller.QProcess')
    def test_stop_process(self, mock_qprocess_class):
        """Тест остановки процесса."""
        # Мокаем QProcess
        mock_process = Mock()
        mock_qprocess_class.return_value = mock_process
        mock_process.waitForStarted.return_value = True
        mock_process.waitForFinished.return_value = True
        
        # Запускаем процесс
        config = {
            "ORIGINAL_VIDEO": str(self.project_root / "data" / "input_video" / "test.mp4")
        }
        self.process_controller.start_process(config)
        
        # Останавливаем процесс
        result = self.process_controller.stop_process()
        
        self.assertTrue(result)
        self.assertFalse(self.process_controller.is_running)
        mock_process.terminate.assert_called_once()
    
    def test_get_process_info(self):
        """Тест получения информации о процессе."""
        # Тест без запущенного процесса
        info = self.process_controller.get_process_info()
        self.assertEqual(info, {})
        
        # Тест с запущенным процессом (мокаем)
        self.process_controller.is_running = True
        self.process_controller.start_time = 1234567890.0
        
        with patch('gui.process_controller.QProcess') as mock_qprocess_class:
            mock_process = Mock()
            mock_process.processId.return_value = 12345
            mock_qprocess_class.return_value = mock_process
            self.process_controller.process = mock_process
            
            info = self.process_controller.get_process_info()
            
            self.assertIn("pid", info)
            self.assertIn("running", info)
            self.assertIn("start_time", info)
            self.assertIn("elapsed_time", info)
            self.assertEqual(info["pid"], 12345)
            self.assertTrue(info["running"])


class TestProcessControllerIntegration(unittest.TestCase):
    """Интеграционные тесты для ProcessController."""
    
    def setUp(self):
        """Настройка тестового окружения."""
        self.temp_dir = tempfile.mkdtemp()
        self.project_root = Path(self.temp_dir)
        
        # Создаем минимальную структуру
        (self.project_root / "src" / "config").mkdir(parents=True)
        (self.project_root / "data" / "input_video").mkdir(parents=True)
        
        # Создаем тестовый main.py
        main_py_path = self.project_root / "main.py"
        main_py_path.write_text("""
import time
import sys

def main():
    print("Test process started")
    print("INFO: Processing video...")
    for i in range(3):
        print(f"Progress: {i * 33}%")
        time.sleep(0.1)
    print("SUCCESS: Test process completed")
    return 0

if __name__ == "__main__":
    sys.exit(main())
""")
        
        # Создаем тестовый видеофайл
        test_video = self.project_root / "data" / "input_video" / "test.mp4"
        test_video.write_text("fake video content")
        
        self.config_manager = ConfigManager(self.project_root)
        self.process_controller = ProcessController(self.project_root, self.config_manager)
    
    def tearDown(self):
        """Очистка после тестов."""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_full_process_workflow(self):
        """Тест полного рабочего процесса."""
        # Собираем логи
        log_messages = []
        
        def on_log(level, message):
            log_messages.append((level, message))
        
        self.process_controller.log_output.connect(on_log)
        
        # Запускаем процесс
        config = {
            "ORIGINAL_VIDEO": str(self.project_root / "data" / "input_video" / "test.mp4")
        }
        
        result = self.process_controller.start_process(config)
        self.assertTrue(result)
        
        # Ждем завершения процесса
        if self.process_controller.process:
            self.process_controller.process.waitForFinished(5000)  # 5 секунд
        
        # Проверяем, что получили логи
        self.assertGreater(len(log_messages), 0)
        
        # Проверяем, что процесс завершился
        self.assertFalse(self.process_controller.is_running)


if __name__ == "__main__":
    unittest.main()
