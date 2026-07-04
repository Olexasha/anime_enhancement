from __future__ import annotations

import html
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QObject,
    QProcess,
    QProcessEnvironment,
    QSignalBlocker,
    Qt,
    QThread,
    QTimer,
    Signal,
)
from PySide6.QtGui import QIcon, QPainter, QPalette, QTextCursor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.config.dependency_checker import check_environment, format_report, has_errors
from src.config.pipeline_config import (
    FIELD_LABELS,
    FIELD_TOOLTIPS,
    PRESETS,
    PipelineConfig,
    apply_preset,
    configure_app_local_tools,
)
from src.config.runtime_paths import (
    app_root,
    default_data_dir,
    is_frozen,
    logs_parent_dir,
    profiles_dir,
    resource_path,
)

DETAIL_FIELDS = [
    "RESOLUTION",
    "START_BATCH_TO_IMPROVE",
    "END_BATCH_TO_IMPROVE",
    "FRAMES_PER_BATCH",
    "OUTPUT_IMAGE_FORMAT",
    "ENABLE_DENOISE",
    "ENABLE_INTERPOLATION",
    "REALESRGAN_MODEL_NAME",
    "UPSCALE_FACTOR",
    "DENOISE_FACTOR",
    "WAIFU2X_UPSCALE_FACTOR",
    "INTERMEDIATE_VIDEO_ENCODER",
    "INTERMEDIATE_VIDEO_CRF",
    "INTERMEDIATE_VIDEO_PRESET",
    "INTERMEDIATE_VIDEO_PIX_FMT",
    "INTERMEDIATE_VIDEO_CONTAINER",
    "FRAMES_MULTIPLY_FACTOR",
    "ENABLE_UHD_MODE",
    "ENABLE_SPATIAL_TTA_MODE",
    "ENABLE_TEMPORAL_TTA_MODE",
    "KEEP_TEMP_FILES",
    "LOG_LEVEL",
]

LOG_LEVELS = {"debug": 10, "info": 20, "error": 40, "critical": 50}
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
GUI_PROGRESS_RE = re.compile(r"^__GUI_PROGRESS__\|(\d{1,3})\|(.+)$")
FRAME_EXTRACTION_RE = re.compile(
    r"Извлечение (?:фреймов|кадров): \d+/\d+ \((\d{1,3})(?:\.\d+)?%\)"
)
LOG_RECORD_LEVEL_RE = re.compile(
    r"(?:^|\]\s)(DEBUG|INFO|SUCCESS|WARNING|ERROR|CRITICAL):"
)
LOGGER_LINE_RE = re.compile(
    r"^\[(\d{2})\.(\d{2})\.(\d{4})\s+(\d{2}:\d{2}:\d{2})\]\s+"
    r"(DEBUG|INFO|SUCCESS|WARNING|ERROR|CRITICAL):\s*(.*)$"
)
LOG_TIME_RE = re.compile(r"^\[\d{2}:\d{2}:\d{2}\]\s+")
OVERALL_PROGRESS_RE = re.compile(r"^Общий прогресс\s*:\s*\d{1,3}%$", re.IGNORECASE)
DONE_PROGRESS_RE = re.compile(r"^ГОТОВО\s*:?\s*(.*)$", re.IGNORECASE)
LOCAL_PROGRESS_RE = re.compile(r"^Прогресс этапа\s*:\s*(.+)$", re.IGNORECASE)
MAX_QUEUE_VIDEOS = 5
QUEUE_STATUS_PENDING = "Ожидает"
QUEUE_STATUS_RUNNING = "В обработке"
QUEUE_STATUS_DONE = "Готово"
QUEUE_STATUS_ERROR = "Ошибка"
QUEUE_STATUS_CANCELLED = "Остановлено"


def decode_process_line(data: bytes) -> str:
    """Декодирует строки QProcess: UTF-8 для исправленной сборки, fallback для Windows."""
    for encoding in ("utf-8", "cp1251", "cp866"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


class IntStepper(QWidget):
    valueChanged = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self._minimum = 0
        self._maximum = 100000
        self._value = 0
        self.setObjectName("intStepper")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.decrease_button = QPushButton("-")
        self.decrease_button.setObjectName("stepperButton")
        self.decrease_button.setToolTip("Уменьшить значение")
        self.decrease_button.clicked.connect(lambda: self.setValue(self._value - 1))

        self.value_edit = QLineEdit("0")
        self.value_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.value_edit.editingFinished.connect(self._commit_text)

        self.increase_button = QPushButton("+")
        self.increase_button.setObjectName("stepperButton")
        self.increase_button.setToolTip("Увеличить значение")
        self.increase_button.clicked.connect(lambda: self.setValue(self._value + 1))

        layout.addWidget(self.decrease_button)
        layout.addWidget(self.value_edit, 1)
        layout.addWidget(self.increase_button)

    def setRange(self, minimum: int, maximum: int) -> None:
        self._minimum = minimum
        self._maximum = maximum
        self.setValue(self._value)

    def setValue(self, value: int) -> None:
        new_value = max(self._minimum, min(self._maximum, int(value)))
        changed = new_value != self._value
        self._value = new_value
        if self.value_edit.text() != str(new_value):
            self.value_edit.setText(str(new_value))
        if changed:
            self.valueChanged.emit(new_value)

    def value(self) -> int:
        return self._value

    def setToolTip(self, text: str) -> None:
        super().setToolTip(text)
        self.value_edit.setToolTip(text)
        self.decrease_button.setToolTip(f"{text}\n\nКнопка '-' уменьшает значение.")
        self.increase_button.setToolTip(f"{text}\n\nКнопка '+' увеличивает значение.")

    def _commit_text(self) -> None:
        try:
            self.setValue(int(self.value_edit.text().strip()))
        except ValueError:
            self.value_edit.setText(str(self._value))


class ElidedPathLineEdit(QLineEdit):
    def paintEvent(self, event: Any) -> None:
        super().paintEvent(event)
        text = self.text()
        if not text or self.hasFocus() or self.hasSelectedText():
            return
        text_rect = self.rect().adjusted(10, 0, -10, 0)
        metrics = self.fontMetrics()
        if metrics.horizontalAdvance(text) <= text_rect.width():
            return

        painter = QPainter(self)
        painter.fillRect(
            text_rect.adjusted(-2, 2, 2, -2),
            self.palette().brush(QPalette.ColorRole.Base),
        )
        painter.setPen(self.palette().color(QPalette.ColorRole.Text))
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            metrics.elidedText(
                text,
                Qt.TextElideMode.ElideMiddle,
                text_rect.width(),
            ),
        )


@dataclass(slots=True)
class VideoQueueItem:
    input_path: Path
    output_path: Path
    status: str = QUEUE_STATUS_PENDING
    progress: int = 0
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    output_auto: bool = True


class EnvironmentCheckWorker(QObject):
    log_line = Signal(str, str)
    finished = Signal(list)
    failed = Signal(str)

    def __init__(self, config: PipelineConfig, project_root: Path):
        super().__init__()
        self.config = config
        self.project_root = project_root

    def run(self) -> None:
        try:
            self.log_line.emit("info", "Начата проверка окружения...")
            self.log_line.emit(
                "info",
                "Проверяем Python, FFmpeg/ffprobe, AI-бинарники, модели, права записи, диск и Vulkan.",
            )
            checks = check_environment(self.config, self.project_root)
            for line in format_report(checks).splitlines():
                level = "error" if "[ОШИБКА]" in line else "info"
                self.log_line.emit(level, line)
            self.finished.emit(checks)
        except Exception as error:
            self.failed.emit(str(error))


class MainWindow(QMainWindow):
    def __init__(self, project_root: Path):
        super().__init__()
        self.project_root = project_root
        self.profile_dir = profiles_dir()
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir = default_data_dir()
        self.config = PipelineConfig.from_env()
        self.process: QProcess | None = None
        self.env_thread: QThread | None = None
        self.env_worker: EnvironmentCheckWorker | None = None
        self.raw_logs: list[tuple[str, str]] = []
        self.process_output_buffer = b""
        self.logs_paused = False
        self.pending_log_render = False
        self.saved_splitter_sizes: list[int] | None = None
        self.compact_log_height = 88
        self.detail_widgets: dict[str, Any] = {}
        self.detail_labels: dict[str, QLabel] = {}
        self.queue_items: list[VideoQueueItem] = []
        self.queue_base_config: PipelineConfig | None = None
        self.active_queue_index: int | None = None
        self.queue_active = False
        self.queue_stop_requested = False
        self.queue_started_at: datetime | None = None
        self.stop_requested = False
        self._last_progress_value = 0

        self.setWindowTitle("Anime Enhancement")
        self._apply_window_icon()
        self.resize(1240, 820)
        self._build_ui()
        self._populate_from_config(apply_preset(self.config, next(iter(PRESETS))))
        self._append_log("info", "GUI готов к работе.")

    def _apply_window_icon(self) -> None:
        icon_path = resource_path("assets/branding/icon.png")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("appRoot")
        root = QVBoxLayout(central)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        self.header_widget = self._build_header()
        root.addWidget(self.header_widget)
        self.primary_panel = self._build_primary_panel()
        root.addWidget(self.primary_panel)

        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.setChildrenCollapsible(False)
        self.settings_area = self._build_settings_area()
        self.log_area = self._build_log_area()
        self.splitter.addWidget(self.settings_area)
        self.splitter.addWidget(self.log_area)
        self.splitter.setSizes([650, 150])
        root.addWidget(self.splitter, 1)

        self.setCentralWidget(central)
        self.statusBar().showMessage("Готово · добавьте видео в очередь")

    def _build_header(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("hero")
        layout = QGridLayout(frame)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setHorizontalSpacing(14)
        layout.setVerticalSpacing(10)

        title = QLabel("Anime Enhancement")
        title.setObjectName("heroTitle")
        subtitle = QLabel(
            "Апскейл, интерполяция и сборка аниме-видео через ffmpeg и ncnn-vulkan"
        )
        subtitle.setObjectName("heroSubtitle")
        layout.addWidget(title, 0, 0, 1, 4)
        layout.addWidget(subtitle, 1, 0, 1, 4)

        self.progress_status_label = QLabel("Готово")
        self.progress_status_label.setObjectName("progressStatus")
        layout.addWidget(self.progress_status_label, 2, 0, 1, 4)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("%p%")
        layout.addWidget(self.progress, 3, 0, 1, 4)

        self.progress_detail_label = QLabel(
            "Общий прогресс: 0% · Этап: ожидание запуска"
        )
        self.progress_detail_label.setObjectName("progressDetail")
        self.progress_detail_label.setWordWrap(True)
        layout.addWidget(self.progress_detail_label, 4, 0, 1, 4)

        self.check_button = QPushButton("Проверить окружение")
        self.check_button.clicked.connect(self.check_environment_clicked)
        self.start_button = QPushButton("Запустить очередь")
        self.start_button.setObjectName("startButton")
        self.start_button.setEnabled(False)
        self.start_button.clicked.connect(self.start_process)
        self.stop_button = QPushButton("Остановить")
        self.stop_button.setObjectName("stopButton")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_process)

        layout.addWidget(self.check_button, 5, 0)
        layout.addWidget(self.start_button, 5, 1)
        layout.addWidget(self.stop_button, 5, 2)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(spacer, 5, 3)
        return frame

    def _build_primary_panel(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("primaryPanel")
        layout = QGridLayout(frame)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(10)

        # Hidden compatibility fields: PipelineConfig and old profile JSON still
        # carry ORIGINAL_VIDEO/FINAL_VIDEO, while the visible UI uses the queue.
        self.input_edit = ElidedPathLineEdit()
        self.input_edit.setToolTip(FIELD_TOOLTIPS["ORIGINAL_VIDEO"])
        self.input_edit.textChanged.connect(
            lambda value: self._sync_path_field("ORIGINAL_VIDEO", value)
        )

        self.output_dir_edit = ElidedPathLineEdit()
        self.output_dir_edit.setToolTip(
            "Общая директория для итоговых файлов очереди. Имена рассчитываются автоматически."
        )
        self.output_dir_edit.textChanged.connect(self._output_dir_changed)
        self.output_dir_button = QPushButton("Выбрать папку")
        self.output_dir_button.setToolTip(
            "Открыть окно выбора директории для итоговых видео."
        )
        self.output_dir_button.clicked.connect(self.choose_output_dir)

        self.primary_preset_combo = QComboBox()
        self.primary_preset_combo.setToolTip(
            "Готовый набор параметров качества и скорости обработки."
        )
        self.primary_preset_combo.addItems(PRESETS.keys())
        self.primary_preset_combo.currentTextChanged.connect(self.apply_selected_preset)

        self.primary_denoise = QCheckBox("Денойз")
        self.primary_denoise.setToolTip(FIELD_TOOLTIPS["ENABLE_DENOISE"])
        self.primary_denoise.toggled.connect(
            lambda value: self._set_bool_field("ENABLE_DENOISE", value)
        )
        self.primary_interpolation = QCheckBox("Интерполяция")
        self.primary_interpolation.setToolTip(FIELD_TOOLTIPS["ENABLE_INTERPOLATION"])
        self.primary_interpolation.toggled.connect(
            lambda value: self._set_bool_field("ENABLE_INTERPOLATION", value)
        )

        self.final_path_label = ElidedPathLineEdit(
            "Итоговый файл рассчитывается в строках очереди."
        )
        self.final_path_label.setObjectName("computedPath")
        self.final_path_label.setReadOnly(True)
        self.final_path_label.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

        self.queue_summary_label = QLabel(
            f"0/{MAX_QUEUE_VIDEOS} видео · обработка строго по одному"
        )
        self.queue_summary_label.setObjectName("queueHint")
        self.queue_table = QTableWidget(0, 6)
        self.queue_table.setObjectName("queueTable")
        self.queue_table.setHorizontalHeaderLabels(
            ["№", "Входной файл", "Итоговый файл", "Статус", "Прогресс", "Действия"]
        )
        self.queue_table.setMinimumHeight(188)
        self.queue_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.queue_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.queue_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.queue_table.verticalHeader().setVisible(False)
        self.queue_table.verticalHeader().setDefaultSectionSize(38)
        self.queue_table.verticalHeader().setMinimumSectionSize(38)
        self.queue_table.setAlternatingRowColors(False)
        self.queue_table.setShowGrid(False)
        self.queue_table.setToolTip(
            "Видео в очереди будут обрабатываться последовательно, без параллельного запуска."
        )
        header = self.queue_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.queue_table.setColumnWidth(5, 112)

        self.queue_empty_hint = QLabel(
            "Очередь пуста. Добавьте одно или несколько видео через кнопку выше."
        )
        self.queue_empty_hint.setObjectName("queueHint")
        self.queue_empty_hint.setWordWrap(True)

        self.add_queue_button = QPushButton("+ Добавить видео")
        self.add_queue_button.setToolTip(
            f"Выбрать несколько видео и добавить их в очередь. Лимит: {MAX_QUEUE_VIDEOS}."
        )
        self.add_queue_button.clicked.connect(self.choose_queue_videos)
        self.move_queue_up_button = QPushButton("↑")
        self.move_queue_up_button.setToolTip("Поднять выбранное видео в очереди.")
        self.move_queue_up_button.clicked.connect(self.move_selected_queue_item_up)
        self.move_queue_down_button = QPushButton("↓")
        self.move_queue_down_button.setToolTip("Опустить выбранное видео в очереди.")
        self.move_queue_down_button.clicked.connect(self.move_selected_queue_item_down)
        self.remove_queue_button = QPushButton("Удалить выбранное")
        self.remove_queue_button.setToolTip("Удалить выбранное видео из очереди.")
        self.remove_queue_button.clicked.connect(self.remove_selected_queue_item)
        self.clear_queue_button = QPushButton("Очистить очередь")
        self.clear_queue_button.setToolTip("Очистить очередь видео.")
        self.clear_queue_button.clicked.connect(self.clear_queue)

        layout.addWidget(
            self._field_label(
                "Директория результата",
                "Общая директория для итоговых файлов очереди. Имена рассчитываются автоматически.",
            ),
            0,
            0,
        )
        layout.addWidget(self.output_dir_edit, 0, 1)
        layout.addWidget(self.output_dir_button, 0, 2)
        layout.addWidget(
            self._field_label(
                "Пресет качества",
                "Готовый набор безопасных параметров. При смене пресета обновляются быстрые и подробные настройки.",
            ),
            1,
            0,
        )
        layout.addWidget(self.primary_preset_combo, 1, 1)

        toggles = QHBoxLayout()
        toggles.setContentsMargins(0, 0, 0, 0)
        toggles.setSpacing(12)
        toggles.addWidget(self.primary_denoise)
        toggles.addWidget(self.primary_interpolation)
        toggles.addStretch()
        layout.addLayout(toggles, 1, 2)

        queue_header = QHBoxLayout()
        queue_header.setContentsMargins(0, 10, 0, 0)
        queue_header.setSpacing(8)
        queue_title = QLabel("Очередь видео")
        queue_title.setObjectName("sectionTitle")
        queue_header.addWidget(queue_title)
        queue_header.addWidget(self.queue_summary_label)
        queue_header.addStretch()
        queue_header.addWidget(self.add_queue_button)
        queue_header.addWidget(self.move_queue_up_button)
        queue_header.addWidget(self.move_queue_down_button)
        queue_header.addWidget(self.remove_queue_button)
        queue_header.addWidget(self.clear_queue_button)
        layout.addLayout(queue_header, 2, 0, 1, 3)
        layout.addWidget(self.queue_table, 3, 0, 1, 3)
        layout.addWidget(self.queue_empty_hint, 4, 0, 1, 3)
        layout.setColumnStretch(1, 1)
        self._refresh_queue_ui()
        return frame

    def _build_settings_area(self) -> QWidget:
        tabs = QTabWidget()
        tabs.addTab(self._build_simple_tab(), "Быстрые настройки")
        tabs.addTab(self._build_detail_tab(), "Подробные параметры")
        tabs.addTab(self._build_profiles_tab(), "Профили")
        return tabs

    def _build_simple_tab(self) -> QWidget:
        page = QWidget()
        page.setObjectName("settingsPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        card, card_layout = self._section_card("Безопасные настройки")
        form = QFormLayout()
        self._configure_settings_form(form)

        self.simple_denoise = QCheckBox("Включить денойз waifu2x")
        self.simple_denoise.setToolTip(FIELD_TOOLTIPS["ENABLE_DENOISE"])
        self.simple_denoise.toggled.connect(
            lambda value: self._set_bool_field("ENABLE_DENOISE", value)
        )
        form.addRow(
            self._form_label("Денойз", FIELD_TOOLTIPS["ENABLE_DENOISE"]),
            self.simple_denoise,
        )

        self.simple_interpolation = QCheckBox("Включить интерполяцию RIFE")
        self.simple_interpolation.setToolTip(FIELD_TOOLTIPS["ENABLE_INTERPOLATION"])
        self.simple_interpolation.toggled.connect(
            lambda value: self._set_bool_field("ENABLE_INTERPOLATION", value)
        )
        form.addRow(
            self._form_label("Интерполяция", FIELD_TOOLTIPS["ENABLE_INTERPOLATION"]),
            self.simple_interpolation,
        )

        card_layout.addLayout(form)
        layout.addWidget(card)
        note = QLabel(
            "Пресет сверху является главным: при его смене обновляются быстрые и подробные параметры."
        )
        note.setObjectName("hint")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch()
        return page

    def _build_detail_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        page = QWidget()
        page.setObjectName("settingsPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)

        card, card_layout = self._section_card("Все параметры пайплайна")
        form = QFormLayout()
        self._configure_settings_form(form)
        for name in DETAIL_FIELDS:
            widget = self._create_detail_widget(name)
            widget.setToolTip(FIELD_TOOLTIPS.get(name, name))
            self.detail_widgets[name] = widget
            label = self._form_label(
                FIELD_LABELS.get(name, name),
                FIELD_TOOLTIPS.get(name, name),
            )
            self.detail_labels[name] = label
            form.addRow(label, widget)
        card_layout.addLayout(form)
        layout.addWidget(card)
        layout.addStretch()
        scroll.setWidget(page)
        return scroll

    def _build_profiles_tab(self) -> QWidget:
        page = QWidget()
        page.setObjectName("settingsPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        card, card_layout = self._section_card("JSON-профили")
        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(10)
        import_button = QPushButton("Импортировать")
        import_button.setObjectName("profileButton")
        import_button.setMinimumHeight(38)
        import_button.setToolTip("Загрузить настройки из выбранного JSON-профиля.")
        import_button.clicked.connect(self.import_profile_clicked)
        export_button = QPushButton("Экспортировать")
        export_button.setObjectName("profileButton")
        export_button.setMinimumHeight(38)
        export_button.setToolTip("Сохранить текущие настройки в выбранный JSON-файл.")
        export_button.clicked.connect(self.export_profile_clicked)
        buttons.addWidget(import_button)
        buttons.addWidget(export_button)
        card_layout.addWidget(
            self._hint_label(
                "Импортируйте профиль из выбранного файла или экспортируйте текущие настройки."
            )
        )
        card_layout.addLayout(buttons)

        layout.addWidget(card)
        text = QLabel(
            f"При запуске GUI сохраняет служебный профиль в {self.profile_dir}. "
            "Импорт/экспорт позволяет работать с любым JSON-файлом профиля."
        )
        text.setObjectName("hint")
        text.setWordWrap(True)
        layout.addWidget(text)
        layout.addStretch()
        return page

    def _build_log_area(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("logPanel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(10)

        controls = QHBoxLayout()
        label = QLabel("Логи процесса")
        label.setObjectName("sectionTitle")
        controls.addWidget(label)
        controls.addStretch()

        self.level_filter = QComboBox()
        self.level_filter.setToolTip(
            "Минимальный уровень сообщений, которые показываются в логах."
        )
        self.level_filter.addItems(["debug", "info", "error", "critical"])
        self.level_filter.setCurrentText("info")
        self.level_filter.currentTextChanged.connect(self.render_logs)
        controls.addWidget(QLabel("Фильтр"))
        controls.addWidget(self.level_filter)

        self.pause_logs_button = QPushButton("Пауза отображения")
        self.pause_logs_button.setToolTip(
            "Остановить только обновление видимой области логов. Сам процесс обработки продолжит работать."
        )
        self.pause_logs_button.setCheckable(True)
        self.pause_logs_button.toggled.connect(self.toggle_log_pause)
        controls.addWidget(self.pause_logs_button)

        self.expand_logs_button = QPushButton("Развернуть логи")
        self.expand_logs_button.setToolTip(
            "Показать область логов почти на все окно. Повторное нажатие вернет обычный вид."
        )
        self.expand_logs_button.setCheckable(True)
        self.expand_logs_button.toggled.connect(self.toggle_logs_expanded)
        controls.addWidget(self.expand_logs_button)

        clear = QPushButton("Очистить")
        clear.setToolTip("Очистить текущий список логов в GUI.")
        clear.clicked.connect(self.clear_logs)
        export = QPushButton("Экспорт логов")
        export.setToolTip("Сохранить все накопленные логи в текстовый файл.")
        export.clicked.connect(self.export_logs)
        controls.addWidget(clear)
        controls.addWidget(export)
        layout.addLayout(controls)

        self.logs = QTextEdit()
        self.logs.setReadOnly(True)
        self.logs.setObjectName("logsText")
        self.logs.setMinimumHeight(64)
        self.logs.setMaximumHeight(self.compact_log_height)
        layout.addWidget(self.logs, 1)
        return frame

    def _section_card(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("settingsCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(12)

        label = QLabel(title)
        label.setObjectName("cardTitle")
        layout.addWidget(label)
        return card, layout

    def _configure_settings_form(self, form: QFormLayout) -> None:
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(20)
        form.setVerticalSpacing(8)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setLabelAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)

    def _create_detail_widget(self, name: str) -> QWidget:
        if name in {
            "ENABLE_DENOISE",
            "ENABLE_INTERPOLATION",
            "ENABLE_UHD_MODE",
            "ENABLE_SPATIAL_TTA_MODE",
            "ENABLE_TEMPORAL_TTA_MODE",
            "KEEP_TEMP_FILES",
        }:
            checkbox = QCheckBox("включено")
            checkbox.toggled.connect(
                lambda value, field=name: self._sync_config_from_widget(field, value)
            )
            return checkbox
        if name in {
            "START_BATCH_TO_IMPROVE",
            "END_BATCH_TO_IMPROVE",
            "FRAMES_PER_BATCH",
            "UPSCALE_FACTOR",
            "DENOISE_FACTOR",
            "WAIFU2X_UPSCALE_FACTOR",
            "INTERMEDIATE_VIDEO_CRF",
            "FRAMES_MULTIPLY_FACTOR",
        }:
            spin = IntStepper()
            spin.setRange(-1 if name == "DENOISE_FACTOR" else 0, 100000)
            if name in {
                "UPSCALE_FACTOR",
                "WAIFU2X_UPSCALE_FACTOR",
                "FRAMES_MULTIPLY_FACTOR",
            }:
                spin.setRange(1, 8)
            if name == "INTERMEDIATE_VIDEO_CRF":
                spin.setRange(0, 51)
            spin.setMinimumWidth(170)
            spin.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
            spin.valueChanged.connect(
                lambda value, field=name: self._sync_config_from_widget(field, value)
            )
            return spin
        combos = {
            "OUTPUT_IMAGE_FORMAT": ["png", "jpg", "jpeg", "webp"],
            "REALESRGAN_MODEL_NAME": [
                "realesr-animevideov3",
                "realesrgan-x4plus-anime",
                "realesrgan-x4plus",
            ],
            "INTERMEDIATE_VIDEO_ENCODER": ["libx264"],
            "INTERMEDIATE_VIDEO_PRESET": [
                "ultrafast",
                "superfast",
                "veryfast",
                "faster",
                "fast",
                "medium",
                "slow",
                "slower",
                "veryslow",
            ],
            "INTERMEDIATE_VIDEO_PIX_FMT": [
                "yuv420p",
                "yuv422p",
                "yuv444p",
            ],
            "INTERMEDIATE_VIDEO_CONTAINER": ["mkv", "mp4"],
            "RESOLUTION": ["1080p", "2K", "4K", "8K"],
        }
        if name in combos:
            combo = QComboBox()
            combo.addItems(combos[name])
            combo.setEditable(True)
            combo.setMinimumWidth(190)
            combo.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
            combo.currentTextChanged.connect(
                lambda value, field=name: self._sync_config_from_widget(field, value)
            )
            return combo
        edit = (
            ElidedPathLineEdit()
            if name in {"ORIGINAL_VIDEO", "FINAL_VIDEO"}
            else QLineEdit()
        )
        if name in {"ORIGINAL_VIDEO", "FINAL_VIDEO"}:
            edit.setReadOnly(True)
        edit.setMinimumWidth(190)
        edit.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        edit.textChanged.connect(
            lambda value, field=name: self._sync_config_from_widget(field, value)
        )
        return edit

    def _field_label(self, text: str, tooltip: str = "") -> QLabel:
        label = QLabel(text)
        label.setObjectName("fieldLabel")
        if tooltip:
            label.setToolTip(tooltip)
        return label

    def _form_label(self, text: str, tooltip: str = "") -> QLabel:
        label = QLabel(text)
        label.setObjectName("formLabel")
        label.setMinimumWidth(150)
        label.setMaximumWidth(230)
        label.setWordWrap(True)
        label.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Preferred,
        )
        if tooltip:
            label.setToolTip(tooltip)
        return label

    def _hint_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("hint")
        label.setWordWrap(True)
        return label

    def _populate_from_config(self, config: PipelineConfig) -> None:
        self.config = config
        input_blocker = QSignalBlocker(self.input_edit)
        output_blocker = QSignalBlocker(self.output_dir_edit)
        preset_blocker = QSignalBlocker(self.primary_preset_combo)
        primary_denoise_blocker = QSignalBlocker(self.primary_denoise)
        primary_interpolation_blocker = QSignalBlocker(self.primary_interpolation)
        denoise_blocker = QSignalBlocker(self.simple_denoise)
        interpolation_blocker = QSignalBlocker(self.simple_interpolation)
        self.input_edit.setText(config.ORIGINAL_VIDEO)
        self.output_dir_edit.setText(str(Path(config.FINAL_VIDEO).parent))
        self._update_path_tooltips()
        self.primary_preset_combo.setCurrentText(self._matching_preset_name(config))
        self.primary_denoise.setChecked(config.ENABLE_DENOISE)
        self.primary_interpolation.setChecked(config.ENABLE_INTERPOLATION)
        self.simple_denoise.setChecked(config.ENABLE_DENOISE)
        self.simple_interpolation.setChecked(config.ENABLE_INTERPOLATION)
        del input_blocker
        del output_blocker
        del preset_blocker
        del primary_denoise_blocker
        del primary_interpolation_blocker
        del denoise_blocker
        del interpolation_blocker
        if self.queue_items and not self.queue_active and self.process is None:
            self._update_pending_queue_outputs()
        self._sync_config_paths_from_queue_or_primary()

        values = self.config.to_dict()
        for name, widget in self.detail_widgets.items():
            value = values[name]
            widget.blockSignals(True)
            if isinstance(widget, QCheckBox):
                widget.setChecked(bool(value))
            elif isinstance(widget, IntStepper):
                widget.setValue(int(value))
            elif isinstance(widget, QComboBox):
                widget.setCurrentText(str(value))
            elif isinstance(widget, QLineEdit):
                widget.setText(str(value))
            widget.blockSignals(False)

    def _collect_config(self) -> PipelineConfig:
        self._update_final_video_from_primary_fields()
        values = self.config.to_dict()
        for name, widget in self.detail_widgets.items():
            if name in {"ORIGINAL_VIDEO", "FINAL_VIDEO"}:
                continue
            if isinstance(widget, QCheckBox):
                values[name] = widget.isChecked()
            elif isinstance(widget, IntStepper):
                values[name] = widget.value()
            elif isinstance(widget, QComboBox):
                values[name] = widget.currentText().strip()
            elif isinstance(widget, QLineEdit):
                values[name] = widget.text().strip()
        queue_item = self._queue_item_for_config()
        if queue_item is not None:
            values["ORIGINAL_VIDEO"] = str(queue_item.input_path)
            values["FINAL_VIDEO"] = str(queue_item.output_path)
        else:
            values["ORIGINAL_VIDEO"] = self.input_edit.text().strip()
            values["FINAL_VIDEO"] = self.config.FINAL_VIDEO
        self.config = PipelineConfig(**values)
        return self.config

    def _sync_path_field(self, field: str, value: str) -> None:
        self._sync_config_from_widget(field, value)
        if field == "ORIGINAL_VIDEO":
            self._sync_output_dir_to_input_parent(value)
            self._update_final_video_from_primary_fields()
        self._update_path_tooltips()

    def _sync_config_from_widget(self, field: str, value: Any) -> None:
        values = self.config.to_dict()
        values[field] = value
        self.config = PipelineConfig(**values)
        if field == "ORIGINAL_VIDEO" and self.input_edit.text() != str(value):
            self.input_edit.setText(str(value))
        elif field == "FINAL_VIDEO":
            self._set_detail_text("FINAL_VIDEO", str(value))
        if field in {"ORIGINAL_VIDEO", "FINAL_VIDEO"}:
            self._update_path_tooltips()

    def _set_detail_text(self, field: str, value: str) -> None:
        widget = self.detail_widgets.get(field)
        if isinstance(widget, QLineEdit) and widget.text() != value:
            widget.blockSignals(True)
            widget.setText(value)
            widget.blockSignals(False)

    def _output_dir_changed(self, _value: str) -> None:
        self._update_pending_queue_outputs()
        self._sync_config_paths_from_queue_or_primary()
        self._refresh_queue_ui()

    def _sync_output_dir_to_input_parent(self, input_path_text: str) -> None:
        input_path_text = input_path_text.strip()
        if not input_path_text:
            return
        input_path = Path(input_path_text)
        if input_path.parent == Path("."):
            return
        if self.output_dir_edit.text().strip() == str(input_path.parent):
            return
        output_blocker = QSignalBlocker(self.output_dir_edit)
        self.output_dir_edit.setText(str(input_path.parent))
        del output_blocker

    def _update_final_video_from_primary_fields(self) -> None:
        input_text = self.input_edit.text().strip()
        input_path = Path(input_text) if input_text else None
        output_dir_text = self.output_dir_edit.text().strip()
        output_dir = (
            Path(output_dir_text) if output_dir_text else self.data_dir / "output_video"
        )
        stem = input_path.stem if input_path and input_path.stem else "enhanced"
        final_path = output_dir / f"{stem}_enhanced.mp4"
        values = self.config.to_dict()
        values["ORIGINAL_VIDEO"] = str(input_path) if input_path else ""
        values["FINAL_VIDEO"] = str(final_path)
        self.config = PipelineConfig(**values)
        self.final_path_label.setText(str(final_path))
        self.final_path_label.setToolTip(str(final_path))
        self._set_detail_text("ORIGINAL_VIDEO", self.config.ORIGINAL_VIDEO)
        self._set_detail_text("FINAL_VIDEO", self.config.FINAL_VIDEO)
        self._update_path_tooltips()

    def _queue_item_for_config(self) -> VideoQueueItem | None:
        if not self.queue_items:
            return None
        if self.active_queue_index is not None:
            return self.queue_items[self.active_queue_index]
        if hasattr(self, "queue_table"):
            row = self.queue_table.currentRow()
            if 0 <= row < len(self.queue_items):
                return self.queue_items[row]
        return self.queue_items[0]

    def _sync_config_paths_from_queue_or_primary(self) -> None:
        queue_item = self._queue_item_for_config()
        if queue_item is None:
            self._update_final_video_from_primary_fields()
            return

        input_blocker = QSignalBlocker(self.input_edit)
        self.input_edit.setText(str(queue_item.input_path))
        del input_blocker
        values = self.config.to_dict()
        values["ORIGINAL_VIDEO"] = str(queue_item.input_path)
        values["FINAL_VIDEO"] = str(queue_item.output_path)
        self.config = PipelineConfig(**values)
        self.final_path_label.setText(str(queue_item.output_path))
        self.final_path_label.setToolTip(str(queue_item.output_path))
        self._set_detail_text("ORIGINAL_VIDEO", self.config.ORIGINAL_VIDEO)
        self._set_detail_text("FINAL_VIDEO", self.config.FINAL_VIDEO)
        self._update_path_tooltips()

    def _update_path_tooltips(self) -> None:
        input_path = self.input_edit.text().strip()
        output_dir = self.output_dir_edit.text().strip()
        if input_path:
            self.input_edit.setToolTip(
                f"{FIELD_TOOLTIPS['ORIGINAL_VIDEO']}\n\n{input_path}"
            )
            original_detail = self.detail_widgets.get("ORIGINAL_VIDEO")
            if isinstance(original_detail, QLineEdit):
                original_detail.setToolTip(
                    f"{FIELD_TOOLTIPS['ORIGINAL_VIDEO']}\n\n{input_path}"
                )
        if output_dir:
            self.output_dir_edit.setToolTip(
                "Директория, куда будет сохранен итоговый файл. Имя файла рассчитывается автоматически."
                f"\n\n{output_dir}"
            )
        final_path = self.config.FINAL_VIDEO.strip()
        if final_path:
            final_detail = self.detail_widgets.get("FINAL_VIDEO")
            if isinstance(final_detail, QLineEdit):
                final_detail.setToolTip(
                    f"{FIELD_TOOLTIPS['FINAL_VIDEO']}\n\n{final_path}"
                )

    def _matching_preset_name(self, config: PipelineConfig) -> str:
        for name, values in PRESETS.items():
            if all(
                getattr(config, key) == value
                for key, value in values.items()
                if hasattr(config, key)
            ):
                return name
        return next(iter(PRESETS))

    def _set_bool_field(self, field: str, value: bool) -> None:
        primary_map = {
            "ENABLE_DENOISE": getattr(self, "primary_denoise", None),
            "ENABLE_INTERPOLATION": getattr(self, "primary_interpolation", None),
        }
        simple_map = {
            "ENABLE_DENOISE": getattr(self, "simple_denoise", None),
            "ENABLE_INTERPOLATION": getattr(self, "simple_interpolation", None),
        }
        for mapped_widget in (primary_map.get(field), simple_map.get(field)):
            if (
                isinstance(mapped_widget, QCheckBox)
                and mapped_widget.isChecked() != value
            ):
                mapped_widget.blockSignals(True)
                mapped_widget.setChecked(value)
                mapped_widget.blockSignals(False)

        widget = self.detail_widgets.get(field)
        if isinstance(widget, QCheckBox) and widget.isChecked() != value:
            widget.blockSignals(True)
            widget.setChecked(value)
            widget.blockSignals(False)
        self._sync_config_from_widget(field, value)

    def _set_text_field(self, field: str, value: str) -> None:
        widget = self.detail_widgets.get(field)
        if isinstance(widget, QComboBox):
            widget.setCurrentText(value)
        self._sync_config_from_widget(field, value)

    def choose_input_video(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Добавить видео в очередь",
            str(self._queue_dialog_dir()),
            "Видео (*.mp4 *.mkv *.avi *.mov *.webm *.mxf);;Все файлы (*)",
        )
        if path:
            self._add_video_paths_to_queue([Path(path)])

    def _apply_selected_input_video(self, path: Path) -> None:
        input_blocker = QSignalBlocker(self.input_edit)
        self.input_edit.setText(str(path))
        del input_blocker
        if not self.queue_items and self.process is None:
            self._add_video_paths_to_queue([path])
        else:
            self._sync_config_paths_from_queue_or_primary()

    def choose_queue_videos(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Добавить видео в очередь",
            str(self._queue_dialog_dir()),
            "Видео (*.mp4 *.mkv *.avi *.mov *.webm *.mxf);;Все файлы (*)",
        )
        self._add_video_paths_to_queue(Path(path) for path in paths)

    def add_current_video_to_queue(self) -> None:
        input_text = self.input_edit.text().strip()
        if not input_text:
            QMessageBox.information(
                self,
                "Очередь видео",
                "Сначала выберите входное видео или добавьте файлы через кнопку выбора.",
            )
            return
        self._add_video_paths_to_queue([Path(input_text)])

    def _queue_dialog_dir(self) -> Path:
        if self.queue_items:
            return self.queue_items[-1].input_path.parent
        input_text = self.input_edit.text().strip()
        if input_text:
            return Path(input_text).parent
        return self.data_dir / "input_video"

    def _add_video_paths_to_queue(self, paths: Any) -> None:
        if self.process is not None or self.queue_active:
            QMessageBox.information(
                self,
                "Очередь видео",
                "Во время обработки очередь нельзя менять.",
            )
            return

        existing = {item.input_path.resolve() for item in self.queue_items}
        added = 0
        skipped = 0
        for raw_path in paths:
            if len(self.queue_items) >= MAX_QUEUE_VIDEOS:
                skipped += 1
                continue
            path = Path(raw_path)
            resolved = path.resolve()
            if resolved in existing:
                skipped += 1
                continue
            self.queue_items.append(
                VideoQueueItem(path, self._auto_output_path_for_video(path))
            )
            existing.add(resolved)
            added += 1
            self._append_log("info", f"В очередь добавлено видео: {path}")

        if skipped:
            self._append_log(
                "info",
                f"Пропущено видео для очереди: {skipped}. "
                f"Лимит очереди: {MAX_QUEUE_VIDEOS}.",
            )
        if added and hasattr(self, "queue_table"):
            self.queue_table.selectRow(len(self.queue_items) - 1)
            self._sync_config_paths_from_queue_or_primary()
        self._refresh_queue_ui()

    def remove_selected_queue_item(self) -> None:
        if self.process is not None or self.queue_active:
            return
        row = self.queue_table.currentRow()
        self._remove_queue_item(row)

    def _remove_queue_item(self, row: int) -> None:
        if 0 <= row < len(self.queue_items):
            removed = self.queue_items.pop(row)
            self._append_log("info", f"Видео удалено из очереди: {removed.input_path}")
            next_row = min(row, len(self.queue_items) - 1)
            self._refresh_queue_ui()
            if next_row >= 0:
                self.queue_table.selectRow(next_row)
            self._sync_config_paths_from_queue_or_primary()

    def move_selected_queue_item_up(self) -> None:
        self._move_queue_item(self.queue_table.currentRow(), -1)

    def move_selected_queue_item_down(self) -> None:
        self._move_queue_item(self.queue_table.currentRow(), 1)

    def _move_queue_item(self, row: int, direction: int) -> None:
        if self.process is not None or self.queue_active:
            return
        target = row + direction
        if not (
            0 <= row < len(self.queue_items) and 0 <= target < len(self.queue_items)
        ):
            return
        self.queue_items[row], self.queue_items[target] = (
            self.queue_items[target],
            self.queue_items[row],
        )
        self._append_log(
            "info",
            f"Очередь: видео перемещено на позицию {target + 1}: "
            f"{self.queue_items[target].input_path.name}",
        )
        self._refresh_queue_ui()
        self.queue_table.selectRow(target)
        self._sync_config_paths_from_queue_or_primary()

    def clear_queue(self) -> None:
        if self.process is not None or self.queue_active:
            return
        if self.queue_items:
            self.queue_items.clear()
            self.active_queue_index = None
            self.queue_active = False
            self.queue_base_config = None
            self.queue_started_at = None
            self._append_log("info", "Очередь видео очищена.")
            self._refresh_queue_ui()
            self._sync_config_paths_from_queue_or_primary()

    def _refresh_queue_ui(self, running: bool | None = None) -> None:
        if not hasattr(self, "queue_table"):
            return
        selected_row = self.queue_table.currentRow()
        self.queue_table.setRowCount(len(self.queue_items))
        for index, item in enumerate(self.queue_items):
            self.queue_table.setRowHeight(index, 38)
            status = item.status
            if index == self.active_queue_index and status == QUEUE_STATUS_RUNNING:
                status = f"▶ {status}"
            self.queue_table.setItem(
                index,
                0,
                self._queue_cell(
                    str(index + 1),
                    alignment=Qt.AlignmentFlag.AlignCenter,
                ),
            )
            self.queue_table.setItem(
                index,
                1,
                self._queue_cell(item.input_path.name, str(item.input_path)),
            )
            self.queue_table.setItem(
                index,
                2,
                self._queue_cell(item.output_path.name, str(item.output_path)),
            )
            self.queue_table.setItem(
                index,
                3,
                self._queue_cell(
                    status,
                    item.error_message or status,
                    alignment=Qt.AlignmentFlag.AlignCenter,
                ),
            )
            self.queue_table.setItem(
                index,
                4,
                self._queue_cell(
                    f"{item.progress}%",
                    f"Прогресс видео: {item.progress}%",
                    alignment=Qt.AlignmentFlag.AlignCenter,
                ),
            )
            self.queue_table.setCellWidget(index, 5, self._queue_actions_widget(index))

        if running is None:
            running = self.process is not None
        queued_count = len(self.queue_items)
        active_text = "обработка строго по одному"
        if self.queue_active and self.active_queue_index is not None:
            active_text = f"сейчас {self.active_queue_index + 1}/{queued_count}"
        self.queue_summary_label.setText(
            f"{queued_count}/{MAX_QUEUE_VIDEOS} видео · {active_text}"
        )
        self.start_button.setText("Запустить очередь")
        self.start_button.setToolTip(
            "Запустить последовательную обработку очереди."
            if self.queue_items
            else "Добавьте видео в очередь, чтобы запустить обработку."
        )
        can_edit_queue = not running and not self.queue_active
        self.start_button.setEnabled(can_edit_queue and queued_count > 0)
        self.add_queue_button.setEnabled(
            can_edit_queue and queued_count < MAX_QUEUE_VIDEOS
        )
        self.move_queue_up_button.setEnabled(can_edit_queue and queued_count > 1)
        self.move_queue_down_button.setEnabled(can_edit_queue and queued_count > 1)
        self.remove_queue_button.setEnabled(can_edit_queue and queued_count > 0)
        self.clear_queue_button.setEnabled(can_edit_queue and queued_count > 0)
        self.queue_empty_hint.setVisible(queued_count == 0)
        if self.active_queue_index is not None and queued_count:
            self.queue_table.selectRow(self.active_queue_index)
        elif 0 <= selected_row < queued_count:
            self.queue_table.selectRow(selected_row)

    def _queue_cell(
        self,
        text: str,
        tooltip: str = "",
        *,
        alignment: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignVCenter
        | Qt.AlignmentFlag.AlignLeft,
    ) -> QTableWidgetItem:
        cell = QTableWidgetItem(text)
        cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
        cell.setTextAlignment(alignment)
        if tooltip:
            cell.setToolTip(tooltip)
        return cell

    def _queue_actions_widget(self, index: int) -> QWidget:
        widget = QWidget()
        widget.setObjectName("queueActions")
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(4)
        can_edit = self.process is None and not self.queue_active

        up = QPushButton("↑")
        up.setObjectName("queueActionButton")
        up.setToolTip("Поднять видео")
        up.setFixedSize(28, 26)
        up.setEnabled(can_edit and index > 0)
        up.clicked.connect(
            lambda _checked=False, row=index: self._move_queue_item(row, -1)
        )
        down = QPushButton("↓")
        down.setObjectName("queueActionButton")
        down.setToolTip("Опустить видео")
        down.setFixedSize(28, 26)
        down.setEnabled(can_edit and index < len(self.queue_items) - 1)
        down.clicked.connect(
            lambda _checked=False, row=index: self._move_queue_item(row, 1)
        )
        remove = QPushButton("×")
        remove.setObjectName("queueActionButton")
        remove.setToolTip("Удалить видео из очереди")
        remove.setFixedSize(28, 26)
        remove.setEnabled(can_edit)
        remove.clicked.connect(
            lambda _checked=False, row=index: self._remove_queue_item(row)
        )

        layout.addWidget(up)
        layout.addWidget(down)
        layout.addWidget(remove)
        return widget

    def _update_pending_queue_outputs(self) -> None:
        for item in self.queue_items:
            if item.output_auto and item.status == QUEUE_STATUS_PENDING:
                item.output_path = self._auto_output_path_for_video(item.input_path)

    def _auto_output_path_for_video(self, input_path: Path) -> Path:
        output_dir_text = self.output_dir_edit.text().strip()
        output_dir = Path(output_dir_text) if output_dir_text else input_path.parent
        return output_dir / f"{input_path.stem}_enhanced.mp4"

    def _final_path_for_video(self, input_path: Path) -> Path:
        return self._auto_output_path_for_video(input_path)

    def _config_for_queue_item(
        self, item: VideoQueueItem, base_config: PipelineConfig | None = None
    ) -> PipelineConfig:
        config = base_config or self._collect_config()
        values = config.to_dict()
        values["ORIGINAL_VIDEO"] = str(item.input_path)
        values["FINAL_VIDEO"] = str(item.output_path)
        return PipelineConfig(**values)

    def _config_for_video(
        self, input_path: Path, base_config: PipelineConfig | None = None
    ) -> PipelineConfig:
        config = base_config or self._collect_config()
        values = config.to_dict()
        values["ORIGINAL_VIDEO"] = str(input_path)
        values["FINAL_VIDEO"] = str(self._auto_output_path_for_video(input_path))
        return PipelineConfig(**values)

    def choose_output_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "Выберите папку для итогового видео",
            self.output_dir_edit.text() or str(self.data_dir / "output_video"),
        )
        if path:
            self.output_dir_edit.setText(path)
            self._update_pending_queue_outputs()
            self._sync_config_paths_from_queue_or_primary()
            self._refresh_queue_ui()

    def apply_selected_preset(self, preset_name: str) -> None:
        if not preset_name:
            return
        config = apply_preset(self._collect_config(), preset_name)
        self.primary_preset_combo.blockSignals(True)
        self.primary_preset_combo.setCurrentText(preset_name)
        self.primary_preset_combo.blockSignals(False)
        self._populate_from_config(config)
        self._append_log("info", f"Применен пресет: {preset_name}")

    def import_profile_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Импортировать профиль",
            str(self.profile_dir),
            "JSON (*.json);;Все файлы (*)",
        )
        if not path:
            return
        try:
            profile_path = Path(path)
            config = PipelineConfig.from_json(profile_path)
            self._populate_from_config(config)
            self._append_log("info", f"Профиль импортирован: {profile_path}")
        except Exception as error:
            QMessageBox.critical(self, "Ошибка импорта", str(error))

    def export_profile_clicked(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Экспортировать профиль",
            str(self.profile_dir / "profile.json"),
            "JSON (*.json)",
        )
        if path:
            try:
                profile_path = Path(path)
                self._collect_config().save_json(profile_path)
                self._append_log("info", f"Профиль экспортирован: {profile_path}")
            except Exception as error:
                QMessageBox.critical(self, "Ошибка экспорта", str(error))

    def check_environment_clicked(self) -> None:
        if self.env_thread is not None:
            self._append_log("info", "Проверка окружения уже выполняется.")
            return
        config = self._collect_config()
        self._append_log(
            "info", "Запрос проверки окружения принят. UI остается доступным."
        )
        self.check_button.setEnabled(False)
        self.check_button.setText("Проверяем...")
        self.statusBar().showMessage("Проверка окружения")

        self.env_thread = QThread(self)
        self.env_worker = EnvironmentCheckWorker(config, self.project_root)
        self.env_worker.moveToThread(self.env_thread)
        self.env_thread.started.connect(self.env_worker.run)
        self.env_worker.log_line.connect(self._append_log)
        self.env_worker.finished.connect(self.environment_check_finished)
        self.env_worker.failed.connect(self.environment_check_failed)
        self.env_worker.finished.connect(self.env_thread.quit)
        self.env_worker.failed.connect(self.env_thread.quit)
        self.env_thread.finished.connect(self._cleanup_environment_thread)
        self.env_thread.start()

    def environment_check_finished(self, checks: list) -> None:
        if has_errors(checks):
            self._append_log("error", "Проверка окружения завершена: есть ошибки.")
            QMessageBox.warning(
                self, "Проверка окружения", "Окружение не готово. Подробности в логах."
            )
        else:
            self._append_log(
                "info", "Проверка окружения завершена: критических проблем не найдено."
            )
            QMessageBox.information(
                self, "Проверка окружения", "Критических проблем не найдено."
            )
        self.statusBar().showMessage("Готово")

    def environment_check_failed(self, message: str) -> None:
        self._append_log(
            "critical", f"Проверка окружения завершилась ошибкой: {message}"
        )
        QMessageBox.critical(self, "Ошибка проверки", message)
        self.statusBar().showMessage("Ошибка проверки окружения")

    def _cleanup_environment_thread(self) -> None:
        self.check_button.setEnabled(self.process is None)
        self.check_button.setText("Проверить окружение")
        self.env_worker = None
        self.env_thread = None

    def start_process(self) -> None:
        if self.process is not None:
            QMessageBox.warning(self, "Запуск невозможен", "Процесс уже выполняется.")
            return
        if not self.queue_items:
            QMessageBox.information(
                self,
                "Очередь видео",
                "Добавьте хотя бы одно видео в очередь перед запуском.",
            )
            return
        self.start_queue()

    def _confirm_config_can_start(self, config: PipelineConfig) -> bool:
        errors = config.validate(require_input_exists=True)
        if errors:
            QMessageBox.warning(self, "Ошибки в настройках", "\n".join(errors))
            return False
        output_path = Path(config.FINAL_VIDEO)
        if output_path.exists():
            result = QMessageBox.question(
                self,
                "Файл уже существует",
                f"Итоговый файл уже существует:\n{output_path}\n\nПерезаписать его?",
            )
            if result != QMessageBox.StandardButton.Yes:
                return False
        checks = check_environment(config, self.project_root)
        if has_errors(checks):
            self._append_log(
                "error", "Запуск остановлен: проверка окружения не пройдена."
            )
            self._append_log("error", format_report(checks))
            QMessageBox.warning(
                self,
                "Окружение не готово",
                "Исправьте ошибки окружения перед запуском.",
            )
            return False
        return True

    def start_queue(self) -> None:
        queue_configs = self._prepare_queue_configs()
        if queue_configs is None:
            return
        self.queue_base_config = self._collect_config()
        for item in self.queue_items:
            item.status = QUEUE_STATUS_PENDING
            item.progress = 0
            item.error_message = None
            item.started_at = None
            item.finished_at = None
        self.queue_active = True
        self.queue_stop_requested = False
        self.active_queue_index = None
        self.queue_started_at = datetime.now()
        self._append_log(
            "info",
            f"Очередь: подготовлено видео к обработке: {len(self.queue_items)}.",
        )
        self._refresh_queue_ui()
        self._start_next_queue_item()

    def _prepare_queue_configs(self) -> list[PipelineConfig] | None:
        if not self.queue_items:
            QMessageBox.information(self, "Очередь видео", "Очередь пуста.")
            return None

        base_config = self._collect_config()
        configs = [
            self._config_for_queue_item(item, base_config) for item in self.queue_items
        ]
        validation_errors: list[str] = []
        output_paths: list[Path] = []
        for config in configs:
            item_errors = config.validate(require_input_exists=True)
            if item_errors:
                validation_errors.extend(
                    f"{Path(config.ORIGINAL_VIDEO).name}: {error}"
                    for error in item_errors
                )
            output_paths.append(Path(config.FINAL_VIDEO))

        if validation_errors:
            QMessageBox.warning(
                self,
                "Ошибки в очереди",
                "\n".join(validation_errors[:8]),
            )
            return None

        duplicate_outputs = sorted(
            {
                path
                for path in output_paths
                if sum(candidate == path for candidate in output_paths) > 1
            }
        )
        if duplicate_outputs:
            QMessageBox.warning(
                self,
                "Очередь видео",
                "В очереди есть одинаковые итоговые файлы:\n"
                + "\n".join(str(path) for path in duplicate_outputs[:5]),
            )
            return None

        existing_outputs = [path for path in output_paths if path.exists()]
        if existing_outputs:
            preview = "\n".join(str(path) for path in existing_outputs[:5])
            suffix = "\n..." if len(existing_outputs) > 5 else ""
            result = QMessageBox.question(
                self,
                "Файлы уже существуют",
                "Некоторые итоговые файлы уже существуют и будут перезаписаны:\n"
                f"{preview}{suffix}\n\nПродолжить?",
            )
            if result != QMessageBox.StandardButton.Yes:
                return None

        checks = check_environment(configs[0], self.project_root)
        if has_errors(checks):
            self._append_log(
                "error", "Запуск очереди остановлен: проверка окружения не пройдена."
            )
            self._append_log("error", format_report(checks))
            QMessageBox.warning(
                self,
                "Окружение не готово",
                "Исправьте ошибки окружения перед запуском очереди.",
            )
            return None
        return configs

    def _start_next_queue_item(self) -> None:
        if not self.queue_active or self.queue_stop_requested:
            self._finish_queue("Очередь остановлена.")
            return

        next_index = (
            0 if self.active_queue_index is None else self.active_queue_index + 1
        )
        if next_index >= len(self.queue_items):
            self._finish_queue("Очередь завершена.", completed=True)
            self.statusBar().showMessage("Готово · очередь завершена")
            return

        self.active_queue_index = next_index
        item = self.queue_items[next_index]
        item.status = QUEUE_STATUS_RUNNING
        item.progress = 0
        item.error_message = None
        item.started_at = datetime.now()
        base_config = self.queue_base_config or self._collect_config()
        config = self._config_for_queue_item(item, base_config)
        self._populate_from_config(config)
        self._refresh_queue_ui()

        profile_path = self.profile_dir / "last_run_profile.json"
        start_status = f"Этап: запуск; Файл: {item.input_path.name}"
        self._append_log(
            "info",
            f"Очередь: старт обработки {next_index + 1}/{len(self.queue_items)}: "
            f"{item.input_path}",
        )
        if not self._start_config_process(config, profile_path, start_status):
            item.status = QUEUE_STATUS_ERROR
            item.error_message = "Ошибка запуска"
            item.finished_at = datetime.now()
            self._finish_queue("Очередь остановлена: ошибка запуска.")

    def _finish_queue(self, message: str, *, completed: bool = False) -> None:
        success_count = sum(
            1 for item in self.queue_items if item.status == QUEUE_STATUS_DONE
        )
        error_count = sum(
            1 for item in self.queue_items if item.status == QUEUE_STATUS_ERROR
        )
        elapsed_text = self._queue_elapsed_text()
        self.queue_active = False
        self.queue_stop_requested = False
        self.queue_base_config = None
        self.active_queue_index = None
        self.output_dir_edit.setEnabled(True)
        self.output_dir_button.setEnabled(True)
        self.primary_preset_combo.setEnabled(True)
        self.primary_denoise.setEnabled(True)
        self.primary_interpolation.setEnabled(True)
        if completed:
            self._append_log(
                "info",
                f"Очередь завершена: успешно {success_count}, ошибок {error_count}, "
                f"время {elapsed_text}.",
            )
            self._set_main_progress(100, f"ГОТОВО: очередь завершена за {elapsed_text}")
        else:
            self._append_log("info", message)
        self._refresh_queue_ui()

    def _queue_elapsed_text(self) -> str:
        if self.queue_started_at is None:
            return "00:00:00"
        elapsed = datetime.now() - self.queue_started_at
        total_seconds = max(0, int(elapsed.total_seconds()))
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def _start_config_process(
        self, config: PipelineConfig, profile_path: Path, start_status: str
    ) -> bool:
        config.save_json(profile_path)
        self._set_running_state(True)
        self.stop_requested = False
        self._last_progress_value = 0
        self._set_main_progress(0, start_status)
        self._append_log("info", f"Запуск пайплайна с профилем: {profile_path}")

        configure_app_local_tools(self.project_root)
        try:
            program, arguments, workdir = self._pipeline_command(profile_path)
        except FileNotFoundError as error:
            self._append_log("critical", str(error))
            QMessageBox.critical(self, "Запуск невозможен", str(error))
            self._set_running_state(False)
            return False

        process = QProcess(self)
        process.setProgram(str(program))
        process.setArguments(arguments)
        process.setWorkingDirectory(str(workdir))
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONUNBUFFERED", "1")
        env.insert("PYTHONIOENCODING", "utf-8")
        env.insert("PYTHONUTF8", "1")
        env.insert("ANIME_ENHANCEMENT_GUI_PROGRESS", "1")
        env.insert("PATH", os.environ.get("PATH", env.value("PATH")))
        process.setProcessEnvironment(env)
        process.readyReadStandardOutput.connect(self.read_process_output)
        process.finished.connect(self.process_finished)
        process.errorOccurred.connect(self.process_error)
        self.process = process
        self.process_output_buffer = b""
        process.start()
        if not process.waitForStarted(5000):
            self._append_log("critical", "Не удалось запустить процесс Python.")
            self._set_running_state(False)
            self.process = None
            return False
        return True

    def _pipeline_command(self, profile_path: Path) -> tuple[Path, list[str], Path]:
        if is_frozen():
            helper_name = (
                "AnimeEnhancementCLI.exe" if os.name == "nt" else "AnimeEnhancementCLI"
            )
            helper = app_root() / helper_name
            if helper.exists():
                return helper, ["--config", str(profile_path)], app_root()
            return Path(sys.executable), ["--config", str(profile_path)], app_root()

        if os.name == "nt":
            venv_python = self.project_root / ".venv" / "Scripts" / "python.exe"
        else:
            venv_python = self.project_root / ".venv" / "bin" / "python"
        if venv_python.exists():
            return (
                venv_python,
                ["main.py", "--config", str(profile_path)],
                self.project_root,
            )
        return (
            Path(sys.executable),
            ["main.py", "--config", str(profile_path)],
            self.project_root,
        )

    def stop_process(self) -> None:
        if self.process is None:
            return
        self.stop_requested = True
        if self.queue_active:
            self.queue_stop_requested = True
            active_index = self.active_queue_index
            for index, item in enumerate(self.queue_items):
                if active_index is None or index > active_index:
                    item.status = QUEUE_STATUS_CANCELLED
            self._refresh_queue_ui()
        self._append_log("error", "Пользователь запросил остановку процесса.")
        self.process.terminate()
        QTimer.singleShot(5000, self._kill_if_running)

    def _kill_if_running(self) -> None:
        if (
            self.process is not None
            and self.process.state() != QProcess.ProcessState.NotRunning
        ):
            self._append_log(
                "critical",
                "Процесс не завершился мягко и будет принудительно остановлен.",
            )
            self.process.kill()

    def read_process_output(self) -> None:
        if self.process is None:
            return
        self.process_output_buffer += bytes(self.process.readAllStandardOutput())
        while b"\n" in self.process_output_buffer:
            raw_line, self.process_output_buffer = self.process_output_buffer.split(
                b"\n", 1
            )
            self._handle_process_line(decode_process_line(raw_line.rstrip(b"\r")))

    def process_finished(
        self, exit_code: int, exit_status: QProcess.ExitStatus
    ) -> None:
        if self.process_output_buffer:
            self._handle_process_line(decode_process_line(self.process_output_buffer))
            self.process_output_buffer = b""
        success = exit_status == QProcess.ExitStatus.NormalExit and exit_code == 0
        was_queue_item = self.queue_active and self.active_queue_index is not None
        stopped_by_user = self.stop_requested
        if success:
            self._append_log("info", "Процесс завершен успешно.")
            if self.progress.value() < 100:
                self._set_main_progress(100, "ГОТОВО: видео обработано")
        else:
            self._append_log("critical", f"Процесс завершился с кодом {exit_code}.")
        self.process = None
        self._set_running_state(False)
        if was_queue_item:
            self._handle_queue_item_finished(success, stopped_by_user)
        elif success:
            self.statusBar().showMessage("Готово · файл сохранен")
        else:
            self.statusBar().showMessage("Ошибка · см. логи")
        self.stop_requested = False

    def _handle_queue_item_finished(self, success: bool, stopped_by_user: bool) -> None:
        if self.active_queue_index is None:
            self._finish_queue("Очередь остановлена.")
            return

        item = self.queue_items[self.active_queue_index]
        if stopped_by_user:
            item.status = QUEUE_STATUS_CANCELLED
            item.finished_at = datetime.now()
            self._finish_queue("Очередь остановлена пользователем.")
            self.statusBar().showMessage("Остановлено · очередь прервана")
            return

        if success:
            item.status = QUEUE_STATUS_DONE
            item.progress = 100
            item.finished_at = datetime.now()
            self._append_log(
                "info",
                f"Очередь: видео {self.active_queue_index + 1}/{len(self.queue_items)} "
                f"завершено успешно: {item.output_path}",
            )
            self._refresh_queue_ui()
            QTimer.singleShot(0, self._start_next_queue_item)
            return

        item.status = QUEUE_STATUS_ERROR
        item.error_message = "Процесс завершился с ошибкой"
        item.finished_at = datetime.now()
        self._finish_queue("Очередь остановлена из-за ошибки.")
        self.statusBar().showMessage("Ошибка · очередь остановлена")

    def _handle_process_line(self, line: str) -> None:
        clean = ANSI_RE.sub("", line).strip()
        if not clean:
            return
        if self._try_apply_progress_marker(clean):
            return
        self._try_apply_frame_extraction_progress(clean)
        level = self._detect_level(clean)
        self._append_log(level, clean)

    def _try_apply_progress_marker(self, line: str) -> bool:
        match = GUI_PROGRESS_RE.match(line)
        if not match:
            return False
        self._set_main_progress(int(match.group(1)), match.group(2))
        return True

    def _try_apply_frame_extraction_progress(self, line: str) -> None:
        match = FRAME_EXTRACTION_RE.search(line)
        if not match:
            return
        frame_percent = max(0, min(100, int(match.group(1))))
        overall_percent = 2 + round(frame_percent * 8 / 100)
        self._set_main_progress(
            overall_percent,
            f"Этап: Извлечение кадров; Прогресс этапа: {frame_percent}%",
        )

    def _set_main_progress(self, value: int, status: str) -> None:
        safe_value = max(0, min(100, int(value)))
        if safe_value < self._last_progress_value:
            safe_value = self._last_progress_value
        self._last_progress_value = safe_value
        display_value = safe_value
        if self.queue_active and self.active_queue_index is not None:
            display_value = self._queue_overall_progress(safe_value)
            active_item = self.queue_items[self.active_queue_index]
            active_item.progress = safe_value
            if active_item.status != QUEUE_STATUS_ERROR:
                active_item.status = QUEUE_STATUS_RUNNING
            headline, details = self._format_queue_progress_display(
                display_value,
                safe_value,
                status,
            )
            self._refresh_queue_ui(running=True)
        else:
            headline, details = self._format_progress_display(display_value, status)

        self.progress.setValue(display_value)
        self.progress.setFormat(f"{display_value}%")
        self.progress_status_label.setText(headline)
        self.progress_detail_label.setText(details)
        self.progress_detail_label.setVisible(bool(details))
        self.statusBar().showMessage(headline)

    def _queue_overall_progress(self, current_item_progress: int) -> int:
        if not self.queue_items or self.active_queue_index is None:
            return current_item_progress
        completed_items = max(0, self.active_queue_index)
        raw_value = (
            (completed_items + current_item_progress / 100)
            / max(1, len(self.queue_items))
            * 100
        )
        return max(0, min(100, round(raw_value)))

    def _format_queue_progress_display(
        self,
        overall_value: int,
        current_value: int,
        status: str,
    ) -> tuple[str, str]:
        total = len(self.queue_items)
        current_number = (self.active_queue_index or 0) + 1
        active_item = self.queue_items[self.active_queue_index or 0]
        headline = (
            f"Обработка очереди · {current_number} из {total} · "
            f"текущий файл: {active_item.input_path.name}"
        )

        _, single_details = self._format_progress_display(current_value, status)
        details = [
            f"Общий прогресс: {overall_value}%",
            f"Текущее видео: {current_value}%",
        ]
        for segment in single_details.split(" · "):
            segment = segment.strip()
            if not segment or segment.startswith("Общий прогресс"):
                continue
            if segment.startswith("Локально"):
                continue
            details.append(segment)
        return headline, " · ".join(details)

    def _format_progress_display(self, value: int, status: str) -> tuple[str, str]:
        segments = [
            segment.strip()
            for segment in status.split(";")
            if segment.strip() and not OVERALL_PROGRESS_RE.match(segment.strip())
        ]
        done_text = self._done_progress_text(value, segments, status)
        if done_text is not None:
            headline = "Готово" if not done_text else f"Готово · {done_text}"
            return headline, ""

        stage = ""
        batches = ""
        headline_fallback = ""
        details = [f"Общий прогресс: {value}%"]
        for segment in segments:
            label, separator, text = segment.partition(":")
            label = label.strip()
            text = text.strip() if separator else segment

            if label == "Этап" and text:
                stage = text
                details.append(f"Этап: {text}")
            elif label == "Батчи" and text:
                batches = text
            elif label == "Окно" and text.lower().startswith("батчи "):
                batches = text[6:].strip()
            elif LOCAL_PROGRESS_RE.match(segment):
                local = LOCAL_PROGRESS_RE.match(segment)
                if local:
                    details.append(f"Локально: {local.group(1).strip()}")
            elif label == "Скорость" and text:
                details.append(text)
            elif label in {"Прошло", "Осталось", "Кадры", "Выходные кадры"} and text:
                details.append(f"{label}: {text}")
            elif segment:
                headline_fallback = headline_fallback or segment
                details.append(segment)

        headline_parts = ["Обработка"]
        if stage:
            headline_parts.append(stage)
        elif headline_fallback:
            headline_parts.append(headline_fallback)
        if batches:
            headline_parts.append(f"батчи {batches}")
        return " · ".join(headline_parts), " · ".join(details)

    def _done_progress_text(
        self, value: int, segments: list[str], raw_status: str
    ) -> str | None:
        for segment in segments:
            match = DONE_PROGRESS_RE.match(segment)
            if match:
                return match.group(1).strip()
        if value >= 100 and "заверш" in raw_status.lower():
            return "видео обработано"
        return None

    def toggle_logs_expanded(self, expanded: bool) -> None:
        if expanded:
            self.saved_splitter_sizes = self.splitter.sizes()
            self.header_widget.hide()
            self.primary_panel.hide()
            self.settings_area.hide()
            self.expand_logs_button.setText("Свернуть логи")
            self.logs.setMaximumHeight(16777215)
            self.splitter.setSizes([0, 1])
            self.logs.setFocus()
        else:
            self.header_widget.show()
            self.primary_panel.show()
            self.settings_area.show()
            self.expand_logs_button.setText("Развернуть логи")
            self.logs.setMaximumHeight(self.compact_log_height)
            if self.saved_splitter_sizes:
                self.splitter.setSizes(self.saved_splitter_sizes)

    def process_error(self, error: QProcess.ProcessError) -> None:
        self._append_log("critical", f"Ошибка процесса: {error.name}")

    def _set_running_state(self, running: bool) -> None:
        self.start_button.setEnabled(
            not running and not self.queue_active and bool(self.queue_items)
        )
        self.check_button.setEnabled(not running and self.env_thread is None)
        self.stop_button.setEnabled(running)
        self.output_dir_edit.setEnabled(not running and not self.queue_active)
        self.output_dir_button.setEnabled(not running and not self.queue_active)
        self.primary_preset_combo.setEnabled(not running and not self.queue_active)
        self.primary_denoise.setEnabled(not running and not self.queue_active)
        self.primary_interpolation.setEnabled(not running and not self.queue_active)
        self._refresh_queue_ui()
        if running:
            self.statusBar().showMessage("Обработка · запуск")
        elif self.progress.value() < 100:
            self.statusBar().showMessage("Готово")

    def _detect_level(self, text: str) -> str:
        match = LOG_RECORD_LEVEL_RE.search(text)
        if match:
            level = match.group(1)
            if level == "CRITICAL":
                return "critical"
            if level == "ERROR":
                return "error"
            if level == "DEBUG":
                return "debug"
            return "info"

        upper = text.upper()
        if "КРИТИЧЕСК" in upper:
            return "critical"
        if (
            "[ОШИБКА]" in upper
            or upper.startswith("ОШИБ")
            or " ОШИБКА" in upper
            or " ОШИБКИ" in upper
        ):
            return "error"
        if "DEBUG" in upper or "ОТЛАД" in upper:
            return "debug"
        return "info"

    def _append_log(self, level: str, message: str) -> None:
        self.raw_logs.append((level, self._format_log_line(message)))
        if len(self.raw_logs) > 20000:
            self.raw_logs = self.raw_logs[-20000:]
        if not self.logs_paused:
            self.render_logs()
        else:
            self.pending_log_render = True

    def _format_log_line(self, message: str) -> str:
        clean = message.strip()
        record = LOGGER_LINE_RE.match(clean)
        if record:
            time_text = record.group(4)
            level = record.group(5)
            body = record.group(6)
            level_prefix = "" if level in {"INFO", "SUCCESS"} else f"{level}: "
            return f"[{time_text}] {level_prefix}{body}"
        if LOG_TIME_RE.match(clean):
            return clean
        timestamp = datetime.now().strftime("%H:%M:%S")
        return f"[{timestamp}] {clean}"

    def render_logs(self) -> None:
        threshold = LOG_LEVELS[self.level_filter.currentText()]
        colors = {
            "debug": "#7CC7A2",
            "info": "#E7EDF3",
            "error": "#FF6B6B",
            "critical": "#FF6B6B",
        }
        lines = []
        for level, message in self.raw_logs:
            if LOG_LEVELS.get(level, 20) >= threshold:
                color = colors.get(level, "#E7EDF3")
                lines.append(
                    f'<span style="color:{color}">{html.escape(message)}</span>'
                )
        self.logs.setHtml("<br>".join(lines))
        cursor = self.logs.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.logs.setTextCursor(cursor)

    def toggle_log_pause(self, paused: bool) -> None:
        self.logs_paused = paused
        self.pause_logs_button.setText(
            "Продолжить отображение" if paused else "Пауза отображения"
        )
        if not paused and self.pending_log_render:
            self.pending_log_render = False
            self.render_logs()

    def clear_logs(self) -> None:
        self.raw_logs.clear()
        self.logs.clear()

    def export_logs(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Экспортировать логи",
            str(
                logs_parent_dir()
                / "logs"
                / f"gui_logs_{datetime.now():%Y%m%d_%H%M%S}.txt"
            ),
            "Текст (*.txt);;Все файлы (*)",
        )
        if not path:
            return
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            "\n".join(message for _, message in self.raw_logs), encoding="utf-8"
        )
        self._append_log("info", f"Логи экспортированы: {output}")
