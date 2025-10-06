"""
Менеджер конфигурации для GUI.

Обеспечивает загрузку настроек из settings.py и сохранение пользовательских изменений
в settings_gui_override.json с возможностью безопасного отката.
"""

import json
import ast
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import importlib.util
import sys

from PySide6.QtCore import QObject, Signal


class ConfigManager(QObject):
    """Менеджер конфигурации с поддержкой загрузки и сохранения настроек."""
    
    # Сигналы
    config_loaded = Signal(dict)  # при загрузке
    config_saved = Signal(dict)  # при сохранении
    error_occurred = Signal(str)  # при ошибках
    
    def __init__(self, project_root: Path):
        super().__init__()
        self.project_root = project_root
        self.settings_py_path = project_root / "src" / "config" / "settings.py"
        self.override_json_path = project_root / "settings_gui_override.json"
        self.backup_dir = project_root / "backups"
        self.backup_dir.mkdir(exist_ok=True)
        
        self._default_config: Dict[str, Any] = {}
        self._current_config: Dict[str, Any] = {}

        if not self.load_default_config():
            self._default_config = self._get_fallback_config()
            self._current_config = self._default_config.copy()
            self.config_loaded.emit(self._current_config)

    # ------------------------------
    # Загрузка конфигурации
    # ------------------------------

    def load_default_config(self) -> bool:
        """Пробует загрузить конфигурацию из settings.py."""
        try:
            config = self._safe_import_settings()
            if not config:
                config = self._parse_settings_ast()
            if not config:
                return False

            self._default_config = config
            self._current_config = config.copy()
            self.config_loaded.emit(self._current_config)
            return True

        except Exception as e:
            msg = f"Ошибка загрузки конфигурации: {e}"
            self.error_occurred.emit(msg)
            return False
    
    def _safe_import_settings(self) -> Optional[Dict[str, Any]]:
        """Безопасный импорт settings.py через importlib."""
        try:
            spec = importlib.util.spec_from_file_location("settings", str(self.settings_py_path))
            if spec is None or spec.loader is None:
                return None

            settings_module = importlib.util.module_from_spec(spec)
            sys.modules["settings"] = settings_module
            spec.loader.exec_module(settings_module)

            config = {
                attr: getattr(settings_module, attr)
                for attr in dir(settings_module)
                if not attr.startswith("_") and isinstance(getattr(settings_module, attr), (str, int, float, bool, list, dict))
            }

            sys.modules.pop("settings", None)  # удаляем модуль после загрузки
            return config

        except Exception as e:
            return None
    
    def _parse_settings_ast(self) -> Optional[Dict[str, Any]]:
        """Парсинг settings.py через AST (fallback-метод)."""
        try:
            with open(self.settings_py_path, "r", encoding="utf-8") as f:
                content = f.read()

            tree = ast.parse(content)
            config = {}

            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            try:
                                config[target.id] = ast.literal_eval(node.value)
                            except Exception:
                                continue
            return config

        except Exception as e:
            return None
    
    def _get_fallback_config(self) -> Dict[str, Any]:
        """Возврат минимального набора значений, если settings.py не найден."""
        return {
            "ORIGINAL_VIDEO": str(self.project_root / "data" / "input_video" / "naruto_test2.mkv"),
            "AUDIO_PATH": str(self.project_root / "data" / "audio"),
            "TMP_VIDEO_PATH": str(self.project_root / "data" / "tmp_video"),
            "FINAL_VIDEO": str(self.project_root / "data" / "output_video" / "enhanced.mp4"),
            "BATCH_VIDEO_PATH": str(self.project_root / "data" / "video_batches"),
            "INPUT_BATCHES_DIR": str(self.project_root / "data" / "default_frame_batches"),
            "LOGS_DIR": str(self.project_root),
            "OUTPUT_IMAGE_FORMAT": "png",
            "START_BATCH_TO_IMPROVE": 1,
            "END_BATCH_TO_IMPROVE": 0,
            "FRAMES_PER_BATCH": 1000,
            "RESOLUTION": "4K",
            "UPSCALED_BATCHES_DIR": str(self.project_root / "data" / "upscaled_frame_batches"),
            "REALESRGAN_MODEL_DIR": str(self.project_root / "src" / "utils" / "realesrgan" / "models"),
            "REALESRGAN_MODEL_NAME": "realesr-animevideov3",
            "UPSCALE_FACTOR": 2,
            "DENOISED_BATCHES_DIR": str(self.project_root / "data" / "denoised_frame_batches"),
            "DENOISE_FACTOR": 3,
            "WAIFU2X_UPSCALE_FACTOR": 1,
            "WAIFU2X_MODEL_DIR": str(self.project_root / "src" / "utils" / "waifu2x" / "models" / "models-cunet"),
            "INTERPOLATED_BATCHES_DIR": str(self.project_root / "data" / "interpolated_frame_batches"),
            "FRAMES_MULTIPLY_FACTOR": 4,
            "TIME_STEP": 0.25,
            "RIFE_MODEL_DIR": str(self.project_root / "src" / "utils" / "rife" / "models" / "rife-v4.6"),
            "ENABLE_UHD_MODE": True,
            "ENABLE_SPATIAL_TTA_MODE": False,
            "ENABLE_TEMPORAL_TTA_MODE": False,
        }
    
    def get_config(self) -> Dict[str, Any]:
        """Возвращает текущую конфигурацию."""
        return self._current_config.copy()
    
    def get_default_config(self) -> Dict[str, Any]:
        """Возвращает конфигурацию по умолчанию."""
        return self._default_config.copy()
    
    def update_config(self, updates: Dict[str, Any]) -> None:
        """Обновляет текущую конфигурацию."""
        self._current_config.update(updates)
    
    def save_override_config(self) -> bool:
        """Сохраняет изменения в settings_gui_override.json."""
        try:
            override_config = {
                key: value
                for key, value in self._current_config.items()
                if self._default_config.get(key) != value
            }

            with open(self.override_json_path, "w", encoding="utf-8") as f:
                json.dump(override_config, f, indent=2, ensure_ascii=False)

            self.config_saved.emit(override_config)
            return True

        except Exception as e:
            msg = f"Ошибка сохранения конфигурации: {e}"
            self.error_occurred.emit(msg)
            return False

    def load_override_config(self) -> bool:
        """Применяет значения из settings_gui_override.json."""
        try:
            if not self.override_json_path.exists():
                return True

            with open(self.override_json_path, "r", encoding="utf-8") as f:
                override_config = json.load(f)

            self._current_config = self._default_config.copy()
            self._current_config.update(override_config)
            self.config_loaded.emit(self._current_config)
            return True

        except Exception as e:
            msg = f"Ошибка загрузки override: {e}"
            self.error_occurred.emit(msg)
            return False

        # ------------------------------
        # Резервные копии settings.py
        # ------------------------------

    def backup_settings_py(self) -> Optional[Path]:
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = self.backup_dir / f"settings.py.bak.{timestamp}"
            shutil.copy2(self.settings_py_path, backup_path)
            return backup_path
        except Exception as e:
            msg = f"Ошибка создания бэкапа settings.py: {e}"
            self.error_occurred.emit(msg)
            return None
    
    def restore_settings_py(self, backup_path: Path) -> bool:
        try:
            shutil.copy2(backup_path, self.settings_py_path)
            return True
        except Exception as e:
            msg = f"Ошибка восстановления settings.py: {e}"
            self.error_occurred.emit(msg)
            return False
    
    def write_to_settings_py(self) -> bool:
        """Перезаписывает settings.py с обновлёнными значениями."""
        try:
            backup = self.backup_settings_py()
            if not backup:
                return False

            with open(self.settings_py_path, "r", encoding="utf-8") as f:
                content = f.read()

            tree = ast.parse(content)
            new_tree = self._update_ast_values(tree, self._current_config)

            with open(self.settings_py_path, "w", encoding="utf-8") as f:
                f.write(ast.unparse(new_tree))

            return True

        except Exception as e:
            msg = f"Ошибка записи в settings.py: {e}"
            self.error_occurred.emit(msg)
            return False

    def _update_ast_values(self, tree: ast.AST, config: Dict[str, Any]) -> ast.AST:
        """Грубое обновление значений в AST (MVP)."""
        content = ast.unparse(tree)
        for key, value in config.items():
            if key in self._default_config and self._default_config[key] != value:
                old = f"{key} = {repr(self._default_config[key])}"
                new = f"{key} = {repr(value)}"
                content = content.replace(old, new)
        return ast.parse(content)

    def reset_to_defaults(self) -> None:
        """Возвращает текущую конфигурацию к дефолтным значениям."""
        self._current_config = self._default_config.copy()
        self.config_loaded.emit(self._current_config)

    def get_available_backups(self) -> list[Path]:
        """Возвращает список доступных резервных копий."""
        if not self.backup_dir.exists():
            return []
        return sorted(
            self.backup_dir.glob("settings.py.bak.*"),
            key=lambda x: x.stat().st_mtime,
            reverse=True,
        )
