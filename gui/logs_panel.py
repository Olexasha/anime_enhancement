"""
Панель логов с цветовой подсветкой.

Отображает логи процесса в реальном времени с цветовой подсветкой
по уровням (ERROR, WARNING, INFO, SUCCESS, DEBUG).
"""

from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton,
    QLabel, QCheckBox, QFileDialog, QMessageBox
)
from PySide6.QtCore import QTimer
from PySide6.QtGui import QTextCharFormat, QColor, QFont, QTextCursor


class LogsPanel(QWidget):
    """Панель для отображения логов с цветовой подсветкой."""
    
    def __init__(self):
        super().__init__()
        self.setup_ui()
        self.setup_connections()
        
        # Настройки отображения
        self.auto_scroll = True
        self.max_lines = 10000  # Максимальное количество строк в логах
        
        # Таймер для автоскролла
        self.scroll_timer = QTimer()
        self.scroll_timer.timeout.connect(self.auto_scroll_to_bottom)
        self.scroll_timer.setSingleShot(True)
    
    def setup_ui(self):
        """Настройка пользовательского интерфейса."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)
        
        # Заголовок
        title = QLabel("Process Logs")
        title.setObjectName("panelTitle")
        layout.addWidget(title)
        
        # Панель управления
        control_panel = QWidget()
        control_layout = QHBoxLayout(control_panel)
        control_layout.setContentsMargins(0, 0, 0, 0)
        control_layout.setSpacing(10)
        
        # Кнопки управления
        self.clear_btn = QPushButton("🗑️ Clear Logs")
        self.clear_btn.setObjectName("clearButton")
        self.clear_btn.clicked.connect(self.clear_logs)
        
        self.export_btn = QPushButton("💾 Export Logs")
        self.export_btn.setObjectName("exportButton")
        self.export_btn.clicked.connect(self.export_logs)
        
        self.pause_btn = QPushButton("⏸️ Pause")
        self.pause_btn.setObjectName("pauseButton")
        self.pause_btn.setCheckable(True)
        self.pause_btn.clicked.connect(self.toggle_pause)
        
        # Чекбокс автоскролла
        self.auto_scroll_check = QCheckBox("Auto Scroll")
        self.auto_scroll_check.setChecked(True)
        self.auto_scroll_check.toggled.connect(self.toggle_auto_scroll)
        
        # Статистика логов
        self.stats_label = QLabel("Lines: 0")
        self.stats_label.setObjectName("statsLabel")
        
        control_layout.addWidget(self.clear_btn)
        control_layout.addWidget(self.export_btn)
        control_layout.addWidget(self.pause_btn)
        control_layout.addWidget(self.auto_scroll_check)
        control_layout.addStretch()
        control_layout.addWidget(self.stats_label)
        
        layout.addWidget(control_panel)
        
        # Текстовое поле для логов
        self.logs_text = QTextEdit()
        self.logs_text.setObjectName("logsText")
        self.logs_text.setReadOnly(True)
        self.logs_text.setFont(QFont("Consolas", 9))
        
        # Настраиваем прокрутку
        self.logs_text.verticalScrollBar().valueChanged.connect(self.on_scroll_changed)
        
        layout.addWidget(self.logs_text)
        
        # Настраиваем стили
        self.apply_styles()
    
    def setup_connections(self):
        """Настраивает соединения сигналов."""
        pass  # Все соединения уже настроены в setup_ui
    
    def apply_styles(self):
        """Применяет стили к панели логов."""
        style = """
        #logsText {
            background-color: #1e1e1e;
            color: #ffffff;
            border: 1px solid #3c3c3c;
            border-radius: 4px;
            padding: 8px;
        }
        
        #clearButton, #exportButton, #pauseButton {
            background-color: #3498db;
            color: white;
            border: none;
            border-radius: 4px;
            padding: 6px 12px;
            font-size: 12px;
        }
        
        #clearButton:hover, #exportButton:hover, #pauseButton:hover {
            background-color: #2980b9;
        }
        
        #pauseButton:checked {
            background-color: #e74c3c;
        }
        
        #pauseButton:checked:hover {
            background-color: #c0392b;
        }
        
        #statsLabel {
            color: #7f8c8d;
            font-size: 12px;
        }
        """
        
        self.setStyleSheet(style)
    
    def add_log(self, level: str, message: str):
        """Добавляет новую запись в лог."""
        if self.pause_btn.isChecked():
            return  # Не добавляем логи, если пауза включена
        
        # Форматируем время
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]  # Миллисекунды
        
        # Создаем форматированную строку
        formatted_message = f"[{timestamp}] [{level}] {message}"
        
        # Добавляем в текстовое поле с цветовой подсветкой
        self.append_colored_text(formatted_message, level)
        
        # Обновляем статистику
        self.update_stats()
        
        # Автоскролл
        if self.auto_scroll:
            self.scroll_timer.start(10)  # Небольшая задержка для плавности
    
    def append_colored_text(self, text: str, level: str):
        """Добавляет текст с цветовой подсветкой."""
        cursor = self.logs_text.textCursor()
        cursor.movePosition(QTextCursor.End)
        
        # Устанавливаем цвет в зависимости от уровня
        format = QTextCharFormat()
        format.setFont(QFont("Consolas", 9))
        
        if level == "ERROR":
            format.setForeground(QColor("#e74c3c"))  # Красный
        elif level == "WARNING":
            format.setForeground(QColor("#f39c12"))  # Оранжевый
        elif level == "SUCCESS":
            format.setForeground(QColor("#27ae60"))  # Зеленый
        elif level == "INFO":
            format.setForeground(QColor("#3498db"))  # Синий
        elif level == "DEBUG":
            format.setForeground(QColor("#95a5a6"))  # Серый
        else:
            format.setForeground(QColor("#ffffff"))  # Белый
        
        # Вставляем текст
        cursor.insertText(text + "\n", format)
        
        # Ограничиваем количество строк
        self.limit_lines()
    
    def limit_lines(self):
        """Ограничивает количество строк в логах."""
        document = self.logs_text.document()
        if document.blockCount() > self.max_lines:
            # Удаляем первые строки
            cursor = QTextCursor(document)
            cursor.movePosition(QTextCursor.Start)
            
            # Удаляем первые 1000 строк
            for _ in range(1000):
                cursor.movePosition(QTextCursor.Down, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()
    
    def update_stats(self):
        """Обновляет статистику логов."""
        line_count = self.logs_text.document().blockCount()
        self.stats_label.setText(f"Lines: {line_count}")
    
    def clear_logs(self):
        """Очищает все логи."""
        reply = QMessageBox.question(
            self,
            "Очистить логи",
            "Вы уверены, что хотите очистить все логи?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.logs_text.clear()
            self.update_stats()
    
    def export_logs(self):
        """Экспортирует логи в файл."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить логи",
            f"logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            "Text Files (*.txt);;All Files (*)"
        )
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(self.logs_text.toPlainText())
                
                QMessageBox.information(
                    self,
                    "Экспорт завершен",
                    f"Логи сохранены в файл:\n{file_path}"
                )
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Ошибка экспорта",
                    f"Не удалось сохранить логи:\n{str(e)}"
                )
    
    def toggle_pause(self):
        """Переключает режим паузы."""
        if self.pause_btn.isChecked():
            self.pause_btn.setText("▶️ Resume")
            self.add_log("INFO", "Логи приостановлены")
        else:
            self.pause_btn.setText("⏸️ Pause")
            self.add_log("INFO", "Логи возобновлены")
    
    def toggle_auto_scroll(self, enabled: bool):
        """Переключает автоскролл."""
        self.auto_scroll = enabled
        if enabled:
            self.auto_scroll_to_bottom()
    
    def auto_scroll_to_bottom(self):
        """Автоматически прокручивает к концу логов."""
        if self.auto_scroll:
            scrollbar = self.logs_text.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
    
    def on_scroll_changed(self, value: int):
        """Обработчик изменения прокрутки."""
        scrollbar = self.logs_text.verticalScrollBar()
        # Если пользователь прокрутил вверх, отключаем автоскролл
        if value < scrollbar.maximum() - 10:  # 10 пикселей от низа
            self.auto_scroll_check.setChecked(False)
        elif value >= scrollbar.maximum() - 10:
            self.auto_scroll_check.setChecked(True)
    
    def add_system_info(self, info: str):
        """Добавляет системную информацию."""
        self.add_log("INFO", f"System: {info}")
    
    def add_error(self, error: str):
        """Добавляет ошибку."""
        self.add_log("ERROR", f"Error: {error}")
    
    def add_warning(self, warning: str):
        """Добавляет предупреждение."""
        self.add_log("WARNING", f"Warning: {warning}")
    
    def add_success(self, message: str):
        """Добавляет сообщение об успехе."""
        self.add_log("SUCCESS", f"Success: {message}")
    
    def add_debug(self, message: str):
        """Добавляет отладочное сообщение."""
        self.add_log("DEBUG", f"Debug: {message}")
