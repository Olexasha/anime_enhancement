"""
Панель настроек нейронных сетей.

Содержит настройки для Waifu2x, Real-ESRGAN и RIFE с рекомендациями
по использованию VRAM и предупреждениями.
"""

from typing import Dict, Any

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QLabel, QGroupBox,
    QComboBox, QSpinBox, QCheckBox,
    QMessageBox, QTextEdit, QTabWidget
)
from PySide6.QtCore import Signal, QTimer


class NeuralNetworksPanel(QWidget):
    """Панель настроек нейронных сетей."""
    
    # Сигнал об изменении настроек
    settings_changed = Signal(dict)
    
    def __init__(self, config_manager):
        super().__init__()
        self.config_manager = config_manager
        self.setup_ui()
        self.setup_connections()
        
        # Таймер для обновления рекомендаций
        self.recommendation_timer = QTimer()
        self.recommendation_timer.timeout.connect(self.update_recommendations)
        self.recommendation_timer.setSingleShot(True)
    
    def setup_ui(self):
        """Настройка пользовательского интерфейса."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        
        # Заголовок
        title = QLabel("Neural Networks Settings")
        title.setObjectName("panelTitle")
        layout.addWidget(title)
        
        # Создаем табы для разных нейронных сетей
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)
        
        # Таб для Waifu2x
        self.waifu2x_tab = self.create_waifu2x_tab()
        self.tab_widget.addTab(self.waifu2x_tab, "Waifu2x (Denoise)")
        
        # Таб для Real-ESRGAN
        self.realesrgan_tab = self.create_realesrgan_tab()
        self.tab_widget.addTab(self.realesrgan_tab, "Real-ESRGAN (Upscale)")
        
        # Таб для RIFE
        self.rife_tab = self.create_rife_tab()
        self.tab_widget.addTab(self.rife_tab, "RIFE (Interpolation)")
        
        # Панель рекомендаций
        self.recommendations_panel = self.create_recommendations_panel()
        layout.addWidget(self.recommendations_panel)
        
        # Добавляем растягивающийся элемент
        layout.addStretch()
    
    def create_waifu2x_tab(self) -> QWidget:
        """Создает таб настроек Waifu2x."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(15)
        
        # Группа модели
        model_group = QGroupBox("Model Settings")
        model_layout = QFormLayout(model_group)
        model_layout.setSpacing(10)
        
        # Выбор модели
        self.waifu2x_model_combo = QComboBox()
        self.waifu2x_model_combo.addItems([
            "cunet (recommended for anime)",
            "upconv_7_anime_style_art_rgb (for art style)",
            "upconv_7_photo (for photos)"
        ])
        model_layout.addRow("Model:", self.waifu2x_model_combo)
        
        # Уровень шума
        self.waifu2x_noise_spin = QSpinBox()
        self.waifu2x_noise_spin.setMinimum(0)
        self.waifu2x_noise_spin.setMaximum(3)
        self.waifu2x_noise_spin.setValue(3)
        model_layout.addRow("Noise Level:", self.waifu2x_noise_spin)
        
        # Фактор масштабирования
        self.waifu2x_scale_spin = QSpinBox()
        self.waifu2x_scale_spin.setMinimum(1)
        self.waifu2x_scale_spin.setMaximum(4)
        self.waifu2x_scale_spin.setValue(1)
        model_layout.addRow("Scale Factor:", self.waifu2x_scale_spin)
        
        # TTA режим
        self.waifu2x_tta_check = QCheckBox("Enable TTA (Test Time Augmentation)")
        self.waifu2x_tta_check.setToolTip("Улучшает качество, но замедляет обработку в 8 раз")
        model_layout.addRow("TTA Mode:", self.waifu2x_tta_check)
        
        layout.addWidget(model_group)
        
        # Группа путей
        paths_group = QGroupBox("Model Paths")
        paths_layout = QFormLayout(paths_group)
        paths_layout.setSpacing(10)
        
        # Путь к модели Waifu2x
        self.waifu2x_model_path_edit = QLineEdit()
        self.waifu2x_model_path_edit.setReadOnly(True)
        paths_layout.addRow("Model Directory:", self.waifu2x_model_path_edit)
        
        layout.addWidget(paths_group)
        
        return tab
    
    def create_realesrgan_tab(self) -> QWidget:
        """Создает таб настроек Real-ESRGAN."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(15)
        
        # Группа модели
        model_group = QGroupBox("Model Settings")
        model_layout = QFormLayout(model_group)
        model_layout.setSpacing(10)
        
        # Выбор модели
        self.realesrgan_model_combo = QComboBox()
        self.realesrgan_model_combo.addItems([
            "realesr-animevideov3 (recommended for anime)",
            "realesrgan-x4plus-anime (for anime images)",
            "realesrgan-x4plus (general purpose)"
        ])
        model_layout.addRow("Model:", self.realesrgan_model_combo)
        
        # Фактор масштабирования
        self.realesrgan_scale_spin = QSpinBox()
        self.realesrgan_scale_spin.setMinimum(2)
        self.realesrgan_scale_spin.setMaximum(4)
        self.realesrgan_scale_spin.setValue(2)
        model_layout.addRow("Scale Factor:", self.realesrgan_scale_spin)
        
        # TTA режим
        self.realesrgan_tta_check = QCheckBox("Enable TTA (Test Time Augmentation)")
        self.realesrgan_tta_check.setToolTip("Улучшает качество, но замедляет обработку в 8 раз")
        model_layout.addRow("TTA Mode:", self.realesrgan_tta_check)
        
        layout.addWidget(model_group)
        
        # Группа путей
        paths_group = QGroupBox("Model Paths")
        paths_layout = QFormLayout(paths_group)
        paths_layout.setSpacing(10)
        
        # Путь к модели Real-ESRGAN
        self.realesrgan_model_path_edit = QLineEdit()
        self.realesrgan_model_path_edit.setReadOnly(True)
        paths_layout.addRow("Model Directory:", self.realesrgan_model_path_edit)
        
        layout.addWidget(paths_group)
        
        return tab
    
    def create_rife_tab(self) -> QWidget:
        """Создает таб настроек RIFE."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(15)
        
        # Группа модели
        model_group = QGroupBox("Model Settings")
        model_layout = QFormLayout(model_group)
        model_layout.setSpacing(10)
        
        # Выбор модели
        self.rife_model_combo = QComboBox()
        self.rife_model_combo.addItems([
            "rife-v4.6 (latest, recommended)",
            "rife-anime (optimized for anime)",
            "rife-UHD (for high resolution)",
            "rife (standard)"
        ])
        model_layout.addRow("Model:", self.rife_model_combo)
        
        # Множитель кадров
        self.rife_multiply_spin = QSpinBox()
        self.rife_multiply_spin.setMinimum(2)
        self.rife_multiply_spin.setMaximum(8)
        self.rife_multiply_spin.setValue(4)
        self.rife_multiply_spin.setToolTip("2x = 60fps, 4x = 120fps, 8x = 240fps")
        model_layout.addRow("Frame Multiplier:", self.rife_multiply_spin)
        
        layout.addWidget(model_group)
        
        # Группа флагов
        flags_group = QGroupBox("Advanced Flags")
        flags_layout = QFormLayout(flags_group)
        flags_layout.setSpacing(10)
        
        # UHD режим
        self.rife_uhd_check = QCheckBox("Enable UHD Mode (-u)")
        self.rife_uhd_check.setToolTip("Рекомендуется для 4K и выше. Требует больше VRAM")
        flags_layout.addRow("UHD Mode:", self.rife_uhd_check)
        
        # Spatial TTA
        self.rife_spatial_tta_check = QCheckBox("Enable Spatial TTA (-x)")
        self.rife_spatial_tta_check.setToolTip("Улучшает качество, но замедляет обработку")
        flags_layout.addRow("Spatial TTA:", self.rife_spatial_tta_check)
        
        # Temporal TTA
        self.rife_temporal_tta_check = QCheckBox("Enable Temporal TTA (-z)")
        self.rife_temporal_tta_check.setToolTip("Улучшает временную согласованность")
        flags_layout.addRow("Temporal TTA:", self.rife_temporal_tta_check)
        
        layout.addWidget(flags_group)
        
        # Группа производительности
        perf_group = QGroupBox("Performance Settings")
        perf_layout = QFormLayout(perf_group)
        perf_layout.setSpacing(10)
        
        # Потоки загрузки
        self.rife_load_threads_spin = QSpinBox()
        self.rife_load_threads_spin.setMinimum(1)
        self.rife_load_threads_spin.setMaximum(16)
        self.rife_load_threads_spin.setValue(2)
        perf_layout.addRow("Load Threads:", self.rife_load_threads_spin)
        
        # Потоки обработки
        self.rife_proc_threads_spin = QSpinBox()
        self.rife_proc_threads_spin.setMinimum(1)
        self.rife_proc_threads_spin.setMaximum(16)
        self.rife_proc_threads_spin.setValue(4)
        perf_layout.addRow("Process Threads:", self.rife_proc_threads_spin)
        
        # Потоки сохранения
        self.rife_save_threads_spin = QSpinBox()
        self.rife_save_threads_spin.setMinimum(1)
        self.rife_save_threads_spin.setMaximum(16)
        self.rife_save_threads_spin.setValue(2)
        perf_layout.addRow("Save Threads:", self.rife_save_threads_spin)
        
        layout.addWidget(perf_group)
        
        # Группа путей
        paths_group = QGroupBox("Model Paths")
        paths_layout = QFormLayout(paths_group)
        paths_layout.setSpacing(10)
        
        # Путь к модели RIFE
        self.rife_model_path_edit = QLineEdit()
        self.rife_model_path_edit.setReadOnly(True)
        paths_layout.addRow("Model Directory:", self.rife_model_path_edit)
        
        layout.addWidget(paths_group)
        
        return tab
    
    def create_recommendations_panel(self) -> QGroupBox:
        """Создает панель рекомендаций."""
        panel = QGroupBox("Recommendations & Warnings")
        layout = QVBoxLayout(panel)
        layout.setSpacing(10)
        
        # Текстовое поле для рекомендаций
        self.recommendations_text = QTextEdit()
        self.recommendations_text.setMaximumHeight(150)
        self.recommendations_text.setReadOnly(True)
        self.recommendations_text.setObjectName("recommendationsText")
        layout.addWidget(self.recommendations_text)
        
        # Кнопка применения рекомендаций
        self.apply_recommendations_btn = QPushButton("Apply Recommended Settings")
        self.apply_recommendations_btn.setObjectName("recommendButton")
        self.apply_recommendations_btn.clicked.connect(self.apply_recommendations)
        layout.addWidget(self.apply_recommendations_btn)
        
        return panel
    
    def setup_connections(self):
        """Настраивает соединения сигналов."""
        # Подключаем все поля к обработчику изменений
        fields = [
            self.waifu2x_model_combo, self.waifu2x_noise_spin, self.waifu2x_scale_spin,
            self.waifu2x_tta_check, self.realesrgan_model_combo, self.realesrgan_scale_spin,
            self.realesrgan_tta_check, self.rife_model_combo, self.rife_multiply_spin,
            self.rife_uhd_check, self.rife_spatial_tta_check, self.rife_temporal_tta_check,
            self.rife_load_threads_spin, self.rife_proc_threads_spin, self.rife_save_threads_spin
        ]
        
        for field in fields:
            if hasattr(field, 'currentTextChanged'):
                field.currentTextChanged.connect(self.on_settings_changed)
            elif hasattr(field, 'valueChanged'):
                field.valueChanged.connect(self.on_settings_changed)
            elif hasattr(field, 'toggled'):
                field.toggled.connect(self.on_settings_changed)
    
    def on_settings_changed(self):
        """Обработчик изменения настроек."""
        # Запускаем таймер для обновления рекомендаций
        self.recommendation_timer.start(500)  # 500ms задержка
        
        settings = self.get_settings()
        self.settings_changed.emit(settings)
    
    def update_recommendations(self):
        """Обновляет рекомендации на основе текущих настроек."""
        recommendations = []
        warnings = []
        
        # Анализируем настройки RIFE
        if self.rife_uhd_check.isChecked():
            if self.rife_proc_threads_spin.value() > 2:
                warnings.append("⚠️ UHD режим с >2 процессами может вызвать OOM")
                recommendations.append("Рекомендуется: 1-2 процесса для UHD режима")
        
        if self.rife_multiply_spin.value() >= 4:
            if not self.rife_uhd_check.isChecked():
                warnings.append("⚠️ Для 4x+ интерполяции рекомендуется включить UHD режим")
                recommendations.append("Включите UHD режим для стабильной работы")
        
        # Анализируем TTA настройки
        tta_count = sum([
            self.waifu2x_tta_check.isChecked(),
            self.realesrgan_tta_check.isChecked(),
            self.rife_spatial_tta_check.isChecked(),
            self.rife_temporal_tta_check.isChecked()
        ])
        
        if tta_count >= 3:
            warnings.append("⚠️ Много TTA режимов - обработка будет очень медленной")
            recommendations.append("Рассмотрите отключение некоторых TTA режимов")
        
        # Анализируем масштабирование
        total_scale = self.waifu2x_scale_spin.value() * self.realesrgan_scale_spin.value()
        if total_scale >= 8:
            warnings.append("⚠️ Очень высокое общее масштабирование - требует много VRAM")
            recommendations.append("Рекомендуется: общее масштабирование не более 8x")
        
        # Формируем итоговое сообщение
        message_parts = []
        
        if warnings:
            message_parts.append("WARNINGS:")
            message_parts.extend(warnings)
            message_parts.append("")
        
        if recommendations:
            message_parts.append("RECOMMENDATIONS:")
            message_parts.extend(recommendations)
        
        if not warnings and not recommendations:
            message_parts.append("✅ Настройки выглядят оптимально!")
        
        self.recommendations_text.setPlainText("\n".join(message_parts))
    
    def apply_recommendations(self):
        """Применяет рекомендуемые настройки."""
        # Сбрасываем к безопасным значениям
        self.rife_uhd_check.setChecked(True)  # Включаем UHD для стабильности
        self.rife_proc_threads_spin.setValue(2)  # Безопасное количество процессов
        self.rife_load_threads_spin.setValue(2)
        self.rife_save_threads_spin.setValue(2)
        
        # Отключаем избыточные TTA режимы
        self.waifu2x_tta_check.setChecked(False)
        self.realesrgan_tta_check.setChecked(False)
        self.rife_spatial_tta_check.setChecked(False)
        self.rife_temporal_tta_check.setChecked(False)
        
        QMessageBox.information(
            self,
            "Рекомендации применены",
            "Применены безопасные настройки для стабильной работы."
        )
    
    def get_settings(self) -> Dict[str, Any]:
        """Возвращает текущие настройки нейронных сетей."""
        # Определяем модель Waifu2x
        waifu2x_model = self.waifu2x_model_combo.currentText()
        if "cunet" in waifu2x_model:
            waifu2x_model_dir = "models-cunet"
        elif "upconv_7_anime_style_art_rgb" in waifu2x_model:
            waifu2x_model_dir = "models-upconv_7_anime_style_art_rgb"
        else:
            waifu2x_model_dir = "models-upconv_7_photo"
        
        # Определяем модель RIFE
        rife_model = self.rife_model_combo.currentText()
        if "rife-v4.6" in rife_model:
            rife_model_dir = "rife-v4.6"
        elif "rife-anime" in rife_model:
            rife_model_dir = "rife-anime"
        elif "rife-UHD" in rife_model:
            rife_model_dir = "rife-UHD"
        else:
            rife_model_dir = "rife"
        
        return {
            # Waifu2x настройки
            "WAIFU2X_MODEL_DIR": str(self.config_manager.project_root / "src" / "utils" / "waifu2x" / "models" / waifu2x_model_dir),
            "DENOISE_FACTOR": self.waifu2x_noise_spin.value(),
            "WAIFU2X_UPSCALE_FACTOR": self.waifu2x_scale_spin.value(),
            "WAIFU2X_TTA": self.waifu2x_tta_check.isChecked(),
            
            # Real-ESRGAN настройки
            "REALESRGAN_MODEL_NAME": self.realesrgan_model_combo.currentText().split(" ")[0],
            "UPSCALE_FACTOR": self.realesrgan_scale_spin.value(),
            "REALESRGAN_TTA": self.realesrgan_tta_check.isChecked(),
            
            # RIFE настройки
            "RIFE_MODEL_DIR": str(self.config_manager.project_root / "src" / "utils" / "rife" / "models" / rife_model_dir),
            "FRAMES_MULTIPLY_FACTOR": self.rife_multiply_spin.value(),
            "ENABLE_UHD_MODE": self.rife_uhd_check.isChecked(),
            "ENABLE_SPATIAL_TTA_MODE": self.rife_spatial_tta_check.isChecked(),
            "ENABLE_TEMPORAL_TTA_MODE": self.rife_temporal_tta_check.isChecked(),
            
            # Параметры производительности
            "RIFE_LOAD_THREADS": self.rife_load_threads_spin.value(),
            "RIFE_PROC_THREADS": self.rife_proc_threads_spin.value(),
            "RIFE_SAVE_THREADS": self.rife_save_threads_spin.value(),
        }
    
    def load_settings(self, config: Dict[str, Any]):
        """Загружает настройки из конфигурации."""
        # Блокируем сигналы во время загрузки
        self.disconnect_change_signals()
        
        try:
            # Загружаем настройки Waifu2x
            waifu2x_model_dir = config.get("WAIFU2X_MODEL_DIR", "")
            if "models-cunet" in waifu2x_model_dir:
                self.waifu2x_model_combo.setCurrentText("cunet (recommended for anime)")
            elif "models-upconv_7_anime_style_art_rgb" in waifu2x_model_dir:
                self.waifu2x_model_combo.setCurrentText("upconv_7_anime_style_art_rgb (for art style)")
            else:
                self.waifu2x_model_combo.setCurrentText("upconv_7_photo (for photos)")
            
            self.waifu2x_noise_spin.setValue(config.get("DENOISE_FACTOR", 3))
            self.waifu2x_scale_spin.setValue(config.get("WAIFU2X_UPSCALE_FACTOR", 1))
            self.waifu2x_tta_check.setChecked(config.get("WAIFU2X_TTA", False))
            
            # Загружаем настройки Real-ESRGAN
            realesrgan_model = config.get("REALESRGAN_MODEL_NAME", "realesr-animevideov3")
            if "realesr-animevideov3" in realesrgan_model:
                self.realesrgan_model_combo.setCurrentText("realesr-animevideov3 (recommended for anime)")
            elif "realesrgan-x4plus-anime" in realesrgan_model:
                self.realesrgan_model_combo.setCurrentText("realesrgan-x4plus-anime (for anime images)")
            else:
                self.realesrgan_model_combo.setCurrentText("realesrgan-x4plus (general purpose)")
            
            self.realesrgan_scale_spin.setValue(config.get("UPSCALE_FACTOR", 2))
            self.realesrgan_tta_check.setChecked(config.get("REALESRGAN_TTA", False))
            
            # Загружаем настройки RIFE
            rife_model_dir = config.get("RIFE_MODEL_DIR", "")
            if "rife-v4.6" in rife_model_dir:
                self.rife_model_combo.setCurrentText("rife-v4.6 (latest, recommended)")
            elif "rife-anime" in rife_model_dir:
                self.rife_model_combo.setCurrentText("rife-anime (optimized for anime)")
            elif "rife-UHD" in rife_model_dir:
                self.rife_model_combo.setCurrentText("rife-UHD (for high resolution)")
            else:
                self.rife_model_combo.setCurrentText("rife (standard)")
            
            self.rife_multiply_spin.setValue(config.get("FRAMES_MULTIPLY_FACTOR", 4))
            self.rife_uhd_check.setChecked(config.get("ENABLE_UHD_MODE", True))
            self.rife_spatial_tta_check.setChecked(config.get("ENABLE_SPATIAL_TTA_MODE", False))
            self.rife_temporal_tta_check.setChecked(config.get("ENABLE_TEMPORAL_TTA_MODE", False))
            
            # Загружаем параметры производительности
            self.rife_load_threads_spin.setValue(config.get("RIFE_LOAD_THREADS", 2))
            self.rife_proc_threads_spin.setValue(config.get("RIFE_PROC_THREADS", 4))
            self.rife_save_threads_spin.setValue(config.get("RIFE_SAVE_THREADS", 2))
            
            # Обновляем пути к моделям
            self.waifu2x_model_path_edit.setText(waifu2x_model_dir)
            self.realesrgan_model_path_edit.setText(config.get("REALESRGAN_MODEL_DIR", ""))
            self.rife_model_path_edit.setText(rife_model_dir)
            
        finally:
            # Восстанавливаем сигналы
            self.connect_change_signals()
            
            # Обновляем рекомендации
            self.update_recommendations()
    
    def disconnect_change_signals(self):
        """Отключает сигналы изменений."""
        fields = [
            self.waifu2x_model_combo, self.waifu2x_noise_spin, self.waifu2x_scale_spin,
            self.waifu2x_tta_check, self.realesrgan_model_combo, self.realesrgan_scale_spin,
            self.realesrgan_tta_check, self.rife_model_combo, self.rife_multiply_spin,
            self.rife_uhd_check, self.rife_spatial_tta_check, self.rife_temporal_tta_check,
            self.rife_load_threads_spin, self.rife_proc_threads_spin, self.rife_save_threads_spin
        ]
        
        for field in fields:
            if hasattr(field, 'currentTextChanged'):
                field.currentTextChanged.disconnect()
            elif hasattr(field, 'valueChanged'):
                field.valueChanged.disconnect()
            elif hasattr(field, 'toggled'):
                field.toggled.disconnect()
    
    def connect_change_signals(self):
        """Подключает сигналы изменений."""
        self.setup_connections()
