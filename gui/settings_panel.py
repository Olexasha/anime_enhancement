"""
Панель настроек проекта.

Содержит поля для редактирования основных путей и параметров проекта.
"""

from pathlib import Path
from typing import Dict, Any

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QLabel, QGroupBox,
    QFileDialog, QMessageBox, QSpinBox, QComboBox
)
from PySide6.QtCore import Signal


class SettingsPanel(QWidget):
    """Панель настроек проекта."""
    
    # Сигнал об изменении настроек
    settings_changed = Signal(dict)
    
    def __init__(self, config_manager):
        super().__init__()
        self.config_manager = config_manager
        self.setup_ui()
    
    def setup_ui(self):
        """Настройка пользовательского интерфейса."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        
        # Заголовок
        title = QLabel("Project Settings")
        title.setObjectName("panelTitle")
        layout.addWidget(title)
        
        # Группа путей к файлам
        files_group = QGroupBox("File Paths")
        files_layout = QFormLayout(files_group)
        files_layout.setSpacing(10)
        
        # Входное видео
        self.input_video_edit = QLineEdit()
        self.input_video_edit.setPlaceholderText("Select input video file...")
        self.input_video_btn = QPushButton("Browse...")
        self.input_video_btn.clicked.connect(self.browse_input_video)
        
        input_layout = QHBoxLayout()
        input_layout.addWidget(self.input_video_edit)
        input_layout.addWidget(self.input_video_btn)
        files_layout.addRow("Input Video:", input_layout)
        
        # Папка с аудио
        self.audio_path_edit = QLineEdit()
        self.audio_path_btn = QPushButton("Browse...")
        self.audio_path_btn.clicked.connect(self.browse_audio_path)
        
        audio_layout = QHBoxLayout()
        audio_layout.addWidget(self.audio_path_edit)
        audio_layout.addWidget(self.audio_path_btn)
        files_layout.addRow("Audio Directory:", audio_layout)
        
        # Папка с временными видео
        self.tmp_video_edit = QLineEdit()
        self.tmp_video_btn = QPushButton("Browse...")
        self.tmp_video_btn.clicked.connect(self.browse_tmp_video_path)
        
        tmp_layout = QHBoxLayout()
        tmp_layout.addWidget(self.tmp_video_edit)
        tmp_layout.addWidget(self.tmp_video_btn)
        files_layout.addRow("Temporary Video Directory:", tmp_layout)
        
        # Папка с финальным видео
        self.final_video_edit = QLineEdit()
        self.final_video_btn = QPushButton("Browse...")
        self.final_video_btn.clicked.connect(self.browse_final_video_path)
        
        final_layout = QHBoxLayout()
        final_layout.addWidget(self.final_video_edit)
        final_layout.addWidget(self.final_video_btn)
        files_layout.addRow("Output Video Directory:", final_layout)
        
        # Папка с батчами
        self.batch_video_edit = QLineEdit()
        self.batch_video_btn = QPushButton("Browse...")
        self.batch_video_btn.clicked.connect(self.browse_batch_video_path)
        
        batch_layout = QHBoxLayout()
        batch_layout.addWidget(self.batch_video_edit)
        batch_layout.addWidget(self.batch_video_btn)
        files_layout.addRow("Video Batches Directory:", batch_layout)
        
        # Папка с входными батчами
        self.input_batches_edit = QLineEdit()
        self.input_batches_btn = QPushButton("Browse...")
        self.input_batches_btn.clicked.connect(self.browse_input_batches_path)
        
        input_batches_layout = QHBoxLayout()
        input_batches_layout.addWidget(self.input_batches_edit)
        input_batches_layout.addWidget(self.input_batches_btn)
        files_layout.addRow("Input Batches Directory:", input_batches_layout)
        
        layout.addWidget(files_group)
        
        # Группа параметров обработки
        processing_group = QGroupBox("Processing Parameters")
        processing_layout = QFormLayout(processing_group)
        processing_layout.setSpacing(10)
        
        # Формат выходных изображений
        self.image_format_combo = QComboBox()
        self.image_format_combo.addItems(["png", "jpg", "bmp", "tiff"])
        processing_layout.addRow("Output Image Format:", self.image_format_combo)
        
        # Начальный батч для обработки
        self.start_batch_spin = QSpinBox()
        self.start_batch_spin.setMinimum(1)
        self.start_batch_spin.setMaximum(9999)
        processing_layout.addRow("Start Batch:", self.start_batch_spin)
        
        # Конечный батч для обработки (0 = автоопределение)
        self.end_batch_spin = QSpinBox()
        self.end_batch_spin.setMinimum(0)
        self.end_batch_spin.setMaximum(9999)
        self.end_batch_spin.setSpecialValueText("Auto (0)")
        processing_layout.addRow("End Batch:", self.end_batch_spin)
        
        # Количество кадров в батче
        self.frames_per_batch_spin = QSpinBox()
        self.frames_per_batch_spin.setMinimum(100)
        self.frames_per_batch_spin.setMaximum(10000)
        self.frames_per_batch_spin.setSingleStep(100)
        processing_layout.addRow("Frames per Batch:", self.frames_per_batch_spin)
        
        # Разрешение
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems(["1080p", "2K", "4K", "8K"])
        processing_layout.addRow("Target Resolution:", self.resolution_combo)
        
        layout.addWidget(processing_group)
        
        # Группа путей к AI инструментам
        ai_group = QGroupBox("AI Tools Paths")
        ai_layout = QFormLayout(ai_group)
        ai_layout.setSpacing(10)
        
        # Путь к Real-ESRGAN
        self.realesrgan_path_edit = QLineEdit()
        self.realesrgan_path_edit.setReadOnly(True)  # Автоматически определяется
        ai_layout.addRow("Real-ESRGAN Path:", self.realesrgan_path_edit)
        
        # Путь к Waifu2x
        self.waifu2x_path_edit = QLineEdit()
        self.waifu2x_path_edit.setReadOnly(True)  # Автоматически определяется
        ai_layout.addRow("Waifu2x Path:", self.waifu2x_path_edit)
        
        # Путь к RIFE
        self.rife_path_edit = QLineEdit()
        self.rife_path_edit.setReadOnly(True)  # Автоматически определяется
        ai_layout.addRow("RIFE Path:", self.rife_path_edit)
        
        layout.addWidget(ai_group)
        
        # Добавляем растягивающийся элемент
        layout.addStretch()
        
        # Подключаем сигналы изменений
        self.connect_change_signals()
    
    def connect_change_signals(self):
        """Подключает сигналы изменений полей."""
        # Подключаем все поля к обработчику изменений
        fields = [
            self.input_video_edit, self.audio_path_edit, self.tmp_video_edit,
            self.final_video_edit, self.batch_video_edit, self.input_batches_edit,
            self.image_format_combo, self.start_batch_spin, self.end_batch_spin,
            self.frames_per_batch_spin, self.resolution_combo
        ]
        
        for field in fields:
            if hasattr(field, 'textChanged'):
                field.textChanged.connect(self.on_settings_changed)
            elif hasattr(field, 'currentTextChanged'):
                field.currentTextChanged.connect(self.on_settings_changed)
            elif hasattr(field, 'valueChanged'):
                field.valueChanged.connect(self.on_settings_changed)
    
    def browse_input_video(self):
        """Открывает диалог выбора входного видео."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите входное видео",
            str(Path(self.input_video_edit.text()).parent) if self.input_video_edit.text() else "",
            "Video Files (*.mp4 *.mkv *.avi *.mov *.wmv);;All Files (*)"
        )
        
        if file_path:
            self.input_video_edit.setText(file_path)
    
    def browse_audio_path(self):
        """Открывает диалог выбора папки с аудио."""
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "Выберите папку с аудио",
            self.audio_path_edit.text() or str(self.config_manager.project_root)
        )
        
        if dir_path:
            self.audio_path_edit.setText(dir_path)
    
    def browse_tmp_video_path(self):
        """Открывает диалог выбора папки с временными видео."""
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "Выберите папку для временных видео",
            self.tmp_video_edit.text() or str(self.config_manager.project_root)
        )
        
        if dir_path:
            self.tmp_video_edit.setText(dir_path)
    
    def browse_final_video_path(self):
        """Открывает диалог выбора папки с финальным видео."""
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "Выберите папку для выходного видео",
            self.final_video_edit.text() or str(self.config_manager.project_root)
        )
        
        if dir_path:
            self.final_video_edit.setText(dir_path)
    
    def browse_batch_video_path(self):
        """Открывает диалог выбора папки с батчами видео."""
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "Выберите папку для батчей видео",
            self.batch_video_edit.text() or str(self.config_manager.project_root)
        )
        
        if dir_path:
            self.batch_video_edit.setText(dir_path)
    
    def browse_input_batches_path(self):
        """Открывает диалог выбора папки с входными батчами."""
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "Выберите папку для входных батчей",
            self.input_batches_edit.text() or str(self.config_manager.project_root)
        )
        
        if dir_path:
            self.input_batches_edit.setText(dir_path)
    
    def on_settings_changed(self):
        """Обработчик изменения настроек."""
        settings = self.get_settings()
        self.settings_changed.emit(settings)
    
    def get_settings(self) -> Dict[str, Any]:
        """Возвращает текущие настройки."""
        return {
            "ORIGINAL_VIDEO": self.input_video_edit.text(),
            "AUDIO_PATH": self.audio_path_edit.text(),
            "TMP_VIDEO_PATH": self.tmp_video_edit.text(),
            "FINAL_VIDEO": self.final_video_edit.text(),
            "BATCH_VIDEO_PATH": self.batch_video_edit.text(),
            "INPUT_BATCHES_DIR": self.input_batches_edit.text(),
            "OUTPUT_IMAGE_FORMAT": self.image_format_combo.currentText(),
            "START_BATCH_TO_IMPROVE": self.start_batch_spin.value(),
            "END_BATCH_TO_IMPROVE": self.end_batch_spin.value(),
            "FRAMES_PER_BATCH": self.frames_per_batch_spin.value(),
            "RESOLUTION": self.resolution_combo.currentText(),
        }
    
    def load_settings(self, config: Dict[str, Any]):
        """Загружает настройки из конфигурации."""
        # Блокируем сигналы во время загрузки
        self.disconnect_change_signals()
        
        try:
            # Загружаем основные пути
            self.input_video_edit.setText(config.get("ORIGINAL_VIDEO", ""))
            self.audio_path_edit.setText(config.get("AUDIO_PATH", ""))
            self.tmp_video_edit.setText(config.get("TMP_VIDEO_PATH", ""))
            self.final_video_edit.setText(config.get("FINAL_VIDEO", ""))
            self.batch_video_edit.setText(config.get("BATCH_VIDEO_PATH", ""))
            self.input_batches_edit.setText(config.get("INPUT_BATCHES_DIR", ""))
            
            # Загружаем параметры обработки
            image_format = config.get("OUTPUT_IMAGE_FORMAT", "png")
            if image_format in [self.image_format_combo.itemText(i) for i in range(self.image_format_combo.count())]:
                self.image_format_combo.setCurrentText(image_format)
            
            self.start_batch_spin.setValue(config.get("START_BATCH_TO_IMPROVE", 1))
            self.end_batch_spin.setValue(config.get("END_BATCH_TO_IMPROVE", 0))
            self.frames_per_batch_spin.setValue(config.get("FRAMES_PER_BATCH", 1000))
            
            resolution = config.get("RESOLUTION", "4K")
            if resolution in [self.resolution_combo.itemText(i) for i in range(self.resolution_combo.count())]:
                self.resolution_combo.setCurrentText(resolution)
            
            # Загружаем пути к AI инструментам (только для отображения)
            self.realesrgan_path_edit.setText(config.get("REALESRGAN_PATH", "Auto-detected"))
            self.waifu2x_path_edit.setText(config.get("WAIFU2X_PATH", "Auto-detected"))
            self.rife_path_edit.setText(config.get("RIFE_PATH", "Auto-detected"))
            
        finally:
            # Восстанавливаем сигналы
            self.connect_change_signals()
    
    def disconnect_change_signals(self):
        """Отключает сигналы изменений."""
        fields = [
            self.input_video_edit, self.audio_path_edit, self.tmp_video_edit,
            self.final_video_edit, self.batch_video_edit, self.input_batches_edit,
            self.image_format_combo, self.start_batch_spin, self.end_batch_spin,
            self.frames_per_batch_spin, self.resolution_combo
        ]
        
        for field in fields:
            if hasattr(field, 'textChanged'):
                field.textChanged.disconnect()
            elif hasattr(field, 'currentTextChanged'):
                field.currentTextChanged.disconnect()
            elif hasattr(field, 'valueChanged'):
                field.valueChanged.disconnect()
    
    def validate_settings(self) -> bool:
        """Проверяет корректность настроек."""
        errors = []
        
        # Проверяем обязательные поля
        if not self.input_video_edit.text():
            errors.append("Не выбран входной видеофайл")
        
        if not self.audio_path_edit.text():
            errors.append("Не указана папка для аудио")
        
        if not self.tmp_video_edit.text():
            errors.append("Не указана папка для временных видео")
        
        if not self.final_video_edit.text():
            errors.append("Не указана папка для выходного видео")
        
        # Проверяем существование входного файла
        input_video = Path(self.input_video_edit.text())
        if self.input_video_edit.text() and not input_video.exists():
            errors.append(f"Входной видеофайл не найден: {input_video}")
        
        if errors:
            QMessageBox.warning(self, "Ошибки в настройках", "\n".join(errors))
            return False
        
        return True
