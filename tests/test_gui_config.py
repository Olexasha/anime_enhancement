"""
Unit тесты для GUI конфигурации.

Тестирует загрузку, сохранение и валидацию конфигурации.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
import os

# Добавляем корневую директорию проекта в путь
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from gui.config import ConfigManager


class TestConfigManager(unittest.TestCase):
    """Тесты для ConfigManager."""
    
    def setUp(self):
        """Настройка тестового окружения."""
        self.temp_dir = tempfile.mkdtemp()
        self.project_root = Path(self.temp_dir)
        
        # Создаем тестовую структуру
        (self.project_root / "src" / "config").mkdir(parents=True)
        (self.project_root / "backups").mkdir(parents=True)
        
        # Создаем тестовый settings.py
        self.settings_py_path = self.project_root / "src" / "config" / "settings.py"
        self.settings_py_path.write_text("""
# Test settings
ORIGINAL_VIDEO = "test_video.mp4"
AUDIO_PATH = "audio/"
TMP_VIDEO_PATH = "tmp/"
FINAL_VIDEO = "output.mp4"
BATCH_VIDEO_PATH = "batches/"
INPUT_BATCHES_DIR = "input_batches/"
OUTPUT_IMAGE_FORMAT = "png"
START_BATCH_TO_IMPROVE = 1
END_BATCH_TO_IMPROVE = 0
FRAMES_PER_BATCH = 1000
RESOLUTION = "4K"
UPSCALED_BATCHES_DIR = "upscaled/"
REALESRGAN_MODEL_DIR = "models/realesrgan/"
REALESRGAN_MODEL_NAME = "realesr-animevideov3"
UPSCALE_FACTOR = 2
DENOISED_BATCHES_DIR = "denoised/"
DENOISE_FACTOR = 3
WAIFU2X_UPSCALE_FACTOR = 1
WAIFU2X_MODEL_DIR = "models/waifu2x/"
INTERPOLATED_BATCHES_DIR = "interpolated/"
FRAMES_MULTIPLY_FACTOR = 4
TIME_STEP = 0.25
RIFE_MODEL_DIR = "models/rife/"
ENABLE_UHD_MODE = True
ENABLE_SPATIAL_TTA_MODE = False
ENABLE_TEMPORAL_TTA_MODE = False
""")
        
        self.config_manager = ConfigManager(self.project_root)
    
    def tearDown(self):
        """Очистка после тестов."""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_load_default_config(self):
        """Тест загрузки конфигурации по умолчанию."""
        config = self.config_manager.get_default_config()
        
        self.assertIsInstance(config, dict)
        self.assertIn("ORIGINAL_VIDEO", config)
        self.assertIn("AUDIO_PATH", config)
        self.assertIn("RESOLUTION", config)
        self.assertEqual(config["RESOLUTION"], "4K")
    
    def test_update_config(self):
        """Тест обновления конфигурации."""
        updates = {
            "ORIGINAL_VIDEO": "new_video.mp4",
            "RESOLUTION": "1080p"
        }
        
        self.config_manager.update_config(updates)
        config = self.config_manager.get_config()
        
        self.assertEqual(config["ORIGINAL_VIDEO"], "new_video.mp4")
        self.assertEqual(config["RESOLUTION"], "1080p")
    
    def test_save_override_config(self):
        """Тест сохранения конфигурации в override файл."""
        updates = {
            "ORIGINAL_VIDEO": "override_video.mp4",
            "RESOLUTION": "2K"
        }
        
        self.config_manager.update_config(updates)
        result = self.config_manager.save_override_config()
        
        self.assertTrue(result)
        self.assertTrue(self.config_manager.override_json_path.exists())
        
        # Проверяем содержимое файла
        with open(self.config_manager.override_json_path, 'r', encoding='utf-8') as f:
            saved_config = json.load(f)
        
        self.assertEqual(saved_config["ORIGINAL_VIDEO"], "override_video.mp4")
        self.assertEqual(saved_config["RESOLUTION"], "2K")
    
    def test_load_override_config(self):
        """Тест загрузки конфигурации из override файла."""
        # Создаем override файл
        override_config = {
            "ORIGINAL_VIDEO": "override_video.mp4",
            "RESOLUTION": "2K"
        }
        
        with open(self.config_manager.override_json_path, 'w', encoding='utf-8') as f:
            json.dump(override_config, f)
        
        # Загружаем конфигурацию
        result = self.config_manager.load_override_config()
        
        self.assertTrue(result)
        config = self.config_manager.get_config()
        self.assertEqual(config["ORIGINAL_VIDEO"], "override_video.mp4")
        self.assertEqual(config["RESOLUTION"], "2K")
    
    def test_reset_to_defaults(self):
        """Тест сброса к значениям по умолчанию."""
        # Изменяем конфигурацию
        self.config_manager.update_config({
            "ORIGINAL_VIDEO": "changed_video.mp4",
            "RESOLUTION": "8K"
        })
        
        # Сбрасываем к умолчанию
        self.config_manager.reset_to_defaults()
        config = self.config_manager.get_config()
        
        # Проверяем, что вернулись значения по умолчанию
        self.assertEqual(config["ORIGINAL_VIDEO"], "test_video.mp4")
        self.assertEqual(config["RESOLUTION"], "4K")
    
    def test_backup_settings_py(self):
        """Тест создания резервной копии settings.py."""
        backup_path = self.config_manager.backup_settings_py()
        
        self.assertIsNotNone(backup_path)
        self.assertTrue(backup_path.exists())
        self.assertIn("settings.py.bak.", backup_path.name)
        
        # Проверяем содержимое
        original_content = self.settings_py_path.read_text()
        backup_content = backup_path.read_text()
        self.assertEqual(original_content, backup_content)
    
    def test_get_available_backups(self):
        """Тест получения списка доступных резервных копий."""
        # Создаем несколько резервных копий
        backup1 = self.config_manager.backup_settings_py()
        backup2 = self.config_manager.backup_settings_py()
        
        backups = self.config_manager.get_available_backups()
        
        self.assertGreaterEqual(len(backups), 2)
        self.assertIn(backup1, backups)
        self.assertIn(backup2, backups)
    
    def test_fallback_config(self):
        """Тест fallback конфигурации при ошибке загрузки."""
        # Удаляем settings.py
        self.settings_py_path.unlink()
        
        # Создаем новый ConfigManager
        config_manager = ConfigManager(self.project_root)
        config = config_manager.get_default_config()
        
        self.assertIsInstance(config, dict)
        self.assertIn("ORIGINAL_VIDEO", config)
        self.assertIn("AUDIO_PATH", config)
    
    @patch('gui.config.importlib.util.spec_from_file_location')
    def test_safe_import_failure(self, mock_spec):
        """Тест обработки ошибки безопасного импорта."""
        # Мокаем ошибку импорта
        mock_spec.return_value = None
        
        config_manager = ConfigManager(self.project_root)
        config = config_manager.get_default_config()
        
        # Должна использоваться fallback конфигурация
        self.assertIsInstance(config, dict)
        self.assertIn("ORIGINAL_VIDEO", config)


class TestConfigIntegration(unittest.TestCase):
    """Интеграционные тесты для конфигурации."""
    
    def setUp(self):
        """Настройка тестового окружения."""
        self.temp_dir = tempfile.mkdtemp()
        self.project_root = Path(self.temp_dir)
        
        # Создаем минимальную структуру
        (self.project_root / "src" / "config").mkdir(parents=True)
        (self.project_root / "backups").mkdir(parents=True)
        
        # Создаем простой settings.py
        settings_content = """
ORIGINAL_VIDEO = "test.mp4"
AUDIO_PATH = "audio/"
RESOLUTION = "4K"
"""
        
        settings_path = self.project_root / "src" / "config" / "settings.py"
        settings_path.write_text(settings_content)
        
        self.config_manager = ConfigManager(self.project_root)
    
    def tearDown(self):
        """Очистка после тестов."""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_full_workflow(self):
        """Тест полного рабочего процесса с конфигурацией."""
        # 1. Загружаем конфигурацию по умолчанию
        default_config = self.config_manager.get_default_config()
        self.assertIn("ORIGINAL_VIDEO", default_config)
        
        # 2. Обновляем конфигурацию
        updates = {
            "ORIGINAL_VIDEO": "updated_video.mp4",
            "RESOLUTION": "1080p"
        }
        self.config_manager.update_config(updates)
        
        # 3. Сохраняем в override файл
        result = self.config_manager.save_override_config()
        self.assertTrue(result)
        
        # 4. Создаем новый ConfigManager и загружаем конфигурацию
        new_config_manager = ConfigManager(self.project_root)
        new_config_manager.load_override_config()
        
        # 5. Проверяем, что изменения сохранились
        final_config = new_config_manager.get_config()
        self.assertEqual(final_config["ORIGINAL_VIDEO"], "updated_video.mp4")
        self.assertEqual(final_config["RESOLUTION"], "1080p")


if __name__ == "__main__":
    unittest.main()
