from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QSplitter, QStackedWidget, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QProgressBar, QStatusBar,
    QMessageBox, QFileDialog
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction

from gui.settings_panel import SettingsPanel
from gui.nn_panel import NeuralNetworksPanel
from gui.logs_panel import LogsPanel
from gui.process_controller import ProcessController
from gui.config import ConfigManager


class MainWindow(QMainWindow):
    """Главное окно приложения."""

    def __init__(self, config_manager: ConfigManager):
        super().__init__()
        self.config_manager = config_manager
        self.process_controller = ProcessController(
            config_manager.project_root,
            config_manager
        )

        self.setup_ui()
        self.setup_connections()
        self.load_config()

        # Таймер для обновления статуса
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_status)
        self.status_timer.start(1000)  # Обновляем каждую секунду

    def setup_ui(self):
        """Настройка пользовательского интерфейса."""
        self.setWindowTitle("Anime Enhancement GUI v1.0")
        self.setMinimumSize(1200, 800)
        self.resize(1400, 900)

        # Центральный виджет
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Главный layout
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Создаем splitter для разделения sidebar и основного контента
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)

        # Sidebar
        self.setup_sidebar(splitter)

        # Основной контент
        self.setup_main_content(splitter)

        # Настройка пропорций splitter
        splitter.setSizes([250, 1150])
        splitter.setCollapsible(0, False)

        # Статус бар
        self.setup_status_bar()

        # Меню
        self.setup_menu_bar()

        # Применяем стили
        self.apply_styles()

    def setup_sidebar(self, parent):
        """Настройка боковой панели навигации."""
        sidebar = QWidget()
        sidebar.setFixedWidth(250)
        sidebar.setObjectName("sidebar")

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Заголовок
        title_label = QLabel("Anime Enhancement")
        title_label.setObjectName("sidebarTitle")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setFixedHeight(60)
        layout.addWidget(title_label)

        # Навигационное меню
        self.nav_list = QListWidget()
        self.nav_list.setObjectName("navList")
        self.nav_list.setMaximumWidth(250)

        # Добавляем пункты меню
        nav_items = [
            ("📁 Project Info", "project"),
            ("⚙️ Settings", "settings"),
            ("🧠 Neural Networks", "neural"),
            ("📋 Logs", "logs")
        ]

        for text, data in nav_items:
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, data)
            self.nav_list.addItem(item)

        self.nav_list.setCurrentRow(0)  # Выбираем первый элемент
        layout.addWidget(self.nav_list)

        # Кнопки управления процессом
        control_layout = QVBoxLayout()
        control_layout.setContentsMargins(10, 10, 10, 10)
        control_layout.setSpacing(10)

        self.start_btn = QPushButton("▶️ Start Processing")
        self.start_btn.setObjectName("startButton")
        self.start_btn.setFixedHeight(40)

        self.stop_btn = QPushButton("⏹️ Stop")
        self.stop_btn.setObjectName("stopButton")
        self.stop_btn.setFixedHeight(40)
        self.stop_btn.setEnabled(False)

        self.pause_btn = QPushButton("⏸️ Pause")
        self.pause_btn.setObjectName("pauseButton")
        self.pause_btn.setFixedHeight(40)
        self.pause_btn.setEnabled(False)

        control_layout.addWidget(self.start_btn)
        control_layout.addWidget(self.stop_btn)
        control_layout.addWidget(self.pause_btn)

        # Кнопки управления настройками
        settings_btn_layout = QVBoxLayout()
        settings_btn_layout.setSpacing(5)

        self.save_btn = QPushButton("💾 Save Settings")
        self.save_btn.setObjectName("saveButton")
        self.save_btn.setFixedHeight(35)

        self.reset_btn = QPushButton("🔄 Reset to Defaults")
        self.reset_btn.setObjectName("resetButton")
        self.reset_btn.setFixedHeight(35)

        settings_btn_layout.addWidget(self.save_btn)
        settings_btn_layout.addWidget(self.reset_btn)

        control_layout.addLayout(settings_btn_layout)
        layout.addLayout(control_layout)

        # Добавляем sidebar в splitter
        parent.addWidget(sidebar)

    def setup_main_content(self, parent):
        """Настройка основного контента."""
        # Stacked widget для переключения между панелями
        self.stacked_widget = QStackedWidget()
        parent.addWidget(self.stacked_widget)

        # Создаем панели
        self.settings_panel = SettingsPanel(self.config_manager)
        self.nn_panel = NeuralNetworksPanel(self.config_manager)
        self.logs_panel = LogsPanel()

        # Добавляем панели в stacked widget
        self.stacked_widget.addWidget(self.settings_panel)  # index 0 - будет заменен на project info
        self.stacked_widget.addWidget(self.settings_panel)  # index 1 - settings
        self.stacked_widget.addWidget(self.nn_panel)        # index 2 - neural networks
        self.stacked_widget.addWidget(self.logs_panel)      # index 3 - logs

        # Создаем панель информации о проекте
        self.project_panel = self.create_project_panel()
        self.stacked_widget.insertWidget(0, self.project_panel)

    def create_project_panel(self) -> QWidget:
        """Создает панель информации о проекте."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        # Заголовок
        title = QLabel("Project Information")
        title.setObjectName("panelTitle")
        layout.addWidget(title)

        # Информация о проекте
        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        info_layout.setSpacing(10)

        # Путь к проекту
        project_path_label = QLabel(f"Project Path: {self.config_manager.project_root}")
        project_path_label.setWordWrap(True)
        info_layout.addWidget(project_path_label)

        # Статус файлов
        status_label = QLabel("File Status:")
        status_label.setObjectName("sectionTitle")
        info_layout.addWidget(status_label)

        # Проверка файлов
        self.check_files_status(info_layout)

        layout.addWidget(info_widget)
        layout.addStretch()

        return panel

    def check_files_status(self, layout: QVBoxLayout):
        """Проверяет статус необходимых файлов."""
        files_to_check = [
            ("main.py", self.config_manager.project_root / "main.py"),
            ("settings.py", self.config_manager.settings_py_path),
            ("Input Video", Path(self.config_manager.get_config().get("ORIGINAL_VIDEO", ""))),
        ]

        for name, path in files_to_check:
            status = "✅" if path.exists() else "❌"
            label = QLabel(f"{status} {name}: {path}")
            label.setWordWrap(True)
            layout.addWidget(label)

    def setup_status_bar(self):
        """Настройка статус бара."""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # Статус процесса
        self.status_label = QLabel("Ready")
        self.status_bar.addWidget(self.status_label)

        # Прогресс бар
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumWidth(200)
        self.status_bar.addPermanentWidget(self.progress_bar)

        # Информация о системе
        self.system_info_label = QLabel("System: Loading...")
        self.status_bar.addPermanentWidget(self.system_info_label)

    def setup_menu_bar(self):
        """Настройка меню."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("File")

        open_video_action = QAction("Open Video...", self)
        open_video_action.triggered.connect(self.open_video_file)
        file_menu.addAction(open_video_action)

        file_menu.addSeparator()

        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Settings menu
        settings_menu = menubar.addMenu("Settings")

        load_config_action = QAction("Load Configuration", self)
        load_config_action.triggered.connect(self.load_config)
        settings_menu.addAction(load_config_action)

        save_config_action = QAction("Save Configuration", self)
        save_config_action.triggered.connect(self.save_config)
        settings_menu.addAction(save_config_action)

        # Help menu
        help_menu = menubar.addMenu("Help")

        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def setup_connections(self):
        """Настройка соединений сигналов и слотов."""
        # Навигация
        self.nav_list.currentRowChanged.connect(self.switch_panel)

        # Кнопки управления процессом
        self.start_btn.clicked.connect(self.start_processing)
        self.stop_btn.clicked.connect(self.stop_processing)
        self.pause_btn.clicked.connect(self.pause_processing)

        # Кнопки настроек
        self.save_btn.clicked.connect(self.save_config)
        self.reset_btn.clicked.connect(self.reset_config)

        # Сигналы от контроллера процессов
        self.process_controller.process_started.connect(self.on_process_started)
        self.process_controller.process_finished.connect(self.on_process_finished)
        self.process_controller.process_error.connect(self.on_process_error)
        self.process_controller.log_output.connect(self.logs_panel.add_log)
        self.process_controller.progress_updated.connect(self.update_progress)

    def switch_panel(self, index: int):
        """Переключает панель в зависимости от выбранного пункта меню."""
        self.stacked_widget.setCurrentIndex(index)

    def start_processing(self):
        """Запускает обработку видео."""
        try:
            # Получаем текущую конфигурацию
            config = self.config_manager.get_config()

            # Запускаем процесс
            if self.process_controller.start_process(config):
                self.logs_panel.add_log("INFO", "Запуск обработки видео...")
            else:
                QMessageBox.warning(self, "Ошибка", "Не удалось запустить процесс обработки")

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка запуска: {str(e)}")

    def stop_processing(self):
        """Останавливает обработку видео."""
        if self.process_controller.stop_process():
            self.logs_panel.add_log("INFO", "Остановка процесса...")

    def pause_processing(self):
        """Приостанавливает обработку видео."""
        if self.process_controller.pause_process():
            self.logs_panel.add_log("INFO", "Процесс приостановлен")

    def save_config(self):
        """Сохраняет конфигурацию."""
        try:
            # Собираем настройки с панелей
            settings = self.settings_panel.get_settings()
            nn_settings = self.nn_panel.get_settings()

            # Обновляем конфигурацию
            self.config_manager.update_config(settings)
            self.config_manager.update_config(nn_settings)

            # Сохраняем
            if self.config_manager.save_override_config():
                QMessageBox.information(self, "Успех", "Настройки сохранены")
                self.logs_panel.add_log("SUCCESS", "Настройки сохранены")
            else:
                QMessageBox.warning(self, "Ошибка", "Не удалось сохранить настройки")

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка сохранения: {str(e)}")

    def reset_config(self):
        """Сбрасывает конфигурацию к значениям по умолчанию."""
        reply = QMessageBox.question(
            self,
            "Подтверждение",
            "Сбросить все настройки к значениям по умолчанию?",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            self.config_manager.reset_to_defaults()
            self.load_config()
            self.logs_panel.add_log("INFO", "Настройки сброшены к значениям по умолчанию")

    def load_config(self):
        """Загружает конфигурацию в панели."""
        try:
            config = self.config_manager.get_config()
            self.settings_panel.load_settings(config)
            self.nn_panel.load_settings(config)
            self.logs_panel.add_log("INFO", "Конфигурация загружена")
        except Exception as e:
            self.logs_panel.add_log("ERROR", f"Ошибка загрузки конфигурации: {str(e)}")

    def open_video_file(self):
        """Открывает диалог выбора видеофайла."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите видеофайл",
            str(self.config_manager.project_root / "data" / "input_video"),
            "Video Files (*.mp4 *.mkv *.avi *.mov *.wmv);;All Files (*)"
        )

        if file_path:
            # Обновляем путь к видео в конфигурации
            self.config_manager.update_config({"ORIGINAL_VIDEO": file_path})
            self.settings_panel.load_settings(self.config_manager.get_config())
            self.logs_panel.add_log("INFO", f"Выбран видеофайл: {file_path}")

    def show_about(self):
        """Показывает диалог "О программе"."""
        QMessageBox.about(
            self,
            "О программе",
            "Anime Enhancement GUI v1.0\n\n"
            "Современный графический интерфейс для улучшения аниме-видео\n"
            "с использованием нейронных сетей (Waifu2x, Real-ESRGAN, RIFE).\n\n"
            "Разработано с использованием PySide6 и Qt6."
        )

    def on_process_started(self):
        """Обработчик запуска процесса."""
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.pause_btn.setEnabled(True)
        self.status_label.setText("Processing...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

    def on_process_finished(self, exit_code: int):
        """Обработчик завершения процесса."""
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.pause_btn.setEnabled(False)

        if exit_code == 0:
            self.status_label.setText("Completed")
            self.progress_bar.setValue(100)
        else:
            self.status_label.setText(f"Failed (exit code: {exit_code})")

        # Скрываем прогресс бар через 5 секунд
        QTimer.singleShot(5000, lambda: self.progress_bar.setVisible(False))

    def on_process_error(self, error_msg: str):
        """Обработчик ошибок процесса."""
        self.status_label.setText("Error")
        QMessageBox.critical(self, "Ошибка процесса", error_msg)

    def update_progress(self, progress: int):
        """Обновляет прогресс выполнения."""
        self.progress_bar.setValue(progress)

    def update_status(self):
        """Обновляет статус системы."""
        try:
            import psutil
            cpu_percent = psutil.cpu_percent()
            memory = psutil.virtual_memory()
            memory_percent = memory.percent

            self.system_info_label.setText(
                f"CPU: {cpu_percent:.1f}% | RAM: {memory_percent:.1f}%"
            )
        except ImportError:
            self.system_info_label.setText("System: psutil not available")

    def apply_styles(self):
        """Применяет стили из styles.qss."""
        try:
            with open("styles.qss", "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())
        except Exception as e:
            print(f"Ошибка загрузки стилей: {e}")

