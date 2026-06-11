from __future__ import annotations

import html
import os
import re
import sys
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
from PySide6.QtGui import QIcon, QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.config.dependency_checker import check_environment, format_report, has_errors
from src.config.pipeline_config import (
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
    "ORIGINAL_VIDEO",
    "FINAL_VIDEO",
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
    "VIDEO_ENCODER",
    "VIDEO_CRF",
    "VIDEO_PRESET",
    "VIDEO_TUNE",
    "VIDEO_NVENC_CQ",
    "VIDEO_PIX_FMT",
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
FRAME_EXTRACTION_RE = re.compile(r"Извлечение фреймов: \d+/\d+ \((\d{1,3})%\)")
LOG_RECORD_LEVEL_RE = re.compile(
    r"(?:^|\]\s)(DEBUG|INFO|SUCCESS|WARNING|ERROR|CRITICAL):"
)


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
        self.detail_widgets: dict[str, Any] = {}

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
        self.splitter.setSizes([520, 300])
        root.addWidget(self.splitter, 1)

        self.setCentralWidget(central)
        self.statusBar().showMessage("Готово")

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

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("Прогресс: %p%")
        layout.addWidget(self.progress, 2, 0, 1, 4)

        self.check_button = QPushButton("Проверить окружение")
        self.check_button.clicked.connect(self.check_environment_clicked)
        self.start_button = QPushButton("Запустить обработку")
        self.start_button.setObjectName("startButton")
        self.start_button.clicked.connect(self.start_process)
        self.stop_button = QPushButton("Остановить")
        self.stop_button.setObjectName("stopButton")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_process)

        layout.addWidget(self.check_button, 3, 0)
        layout.addWidget(self.start_button, 3, 1)
        layout.addWidget(self.stop_button, 3, 2)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(spacer, 3, 3)
        return frame

    def _build_primary_panel(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("primaryPanel")
        layout = QGridLayout(frame)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(10)

        self.input_edit = QLineEdit()
        self.input_edit.setToolTip(FIELD_TOOLTIPS["ORIGINAL_VIDEO"])
        self.input_edit.textChanged.connect(
            lambda value: self._sync_path_field("ORIGINAL_VIDEO", value)
        )
        input_button = QPushButton("Выбрать видео")
        input_button.setToolTip("Открыть окно выбора исходного видеофайла.")
        input_button.clicked.connect(self.choose_input_video)

        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setToolTip(
            "Директория, куда будет сохранен итоговый файл. Имя файла рассчитывается автоматически."
        )
        self.output_dir_edit.textChanged.connect(self._output_dir_changed)
        output_button = QPushButton("Выбрать папку")
        output_button.setToolTip("Открыть окно выбора директории для итогового видео.")
        output_button.clicked.connect(self.choose_output_dir)

        self.primary_preset_combo = QComboBox()
        self.primary_preset_combo.setToolTip(
            "Готовый набор параметров качества и скорости обработки."
        )
        self.primary_preset_combo.addItems(PRESETS.keys())
        self.primary_preset_combo.currentTextChanged.connect(self.apply_selected_preset)

        self.final_path_label = QLabel(
            "Итоговый файл будет рассчитан после выбора входного видео."
        )
        self.final_path_label.setObjectName("computedPath")
        self.final_path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.final_path_label.setWordWrap(True)

        layout.addWidget(
            self._field_label("Входное видео", FIELD_TOOLTIPS["ORIGINAL_VIDEO"]),
            0,
            0,
        )
        layout.addWidget(self.input_edit, 0, 1)
        layout.addWidget(input_button, 0, 2)
        layout.addWidget(
            self._field_label(
                "Директория результата",
                "Директория, куда будет сохранен итоговый файл. Имя файла рассчитывается автоматически.",
            ),
            1,
            0,
        )
        layout.addWidget(self.output_dir_edit, 1, 1)
        layout.addWidget(output_button, 1, 2)
        layout.addWidget(
            self._field_label(
                "Пресет качества",
                "Готовый набор безопасных параметров. При смене пресета обновляются быстрые и подробные настройки.",
            ),
            2,
            0,
        )
        layout.addWidget(self.primary_preset_combo, 2, 1, 1, 2)
        layout.addWidget(
            self._field_label(
                "Итоговый файл",
                "Полный путь к файлу результата. Он рассчитывается из входного видео и директории результата.",
            ),
            3,
            0,
        )
        layout.addWidget(self.final_path_label, 3, 1, 1, 2)
        layout.setColumnStretch(1, 1)
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

        group = QGroupBox("Безопасные настройки")
        group.setObjectName("settingsCard")
        form = QFormLayout(group)

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

        self.simple_encoder = QComboBox()
        self.simple_encoder.setToolTip(FIELD_TOOLTIPS["VIDEO_ENCODER"])
        self.simple_encoder.addItems(["libx264", "h264_nvenc"])
        self.simple_encoder.currentTextChanged.connect(
            lambda value: self._set_text_field("VIDEO_ENCODER", value)
        )
        form.addRow(
            self._form_label("Кодировщик", FIELD_TOOLTIPS["VIDEO_ENCODER"]),
            self.simple_encoder,
        )

        layout.addWidget(group)
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

        group = QGroupBox("Все параметры пайплайна")
        group.setObjectName("settingsCard")
        form = QFormLayout(group)
        form.setSpacing(9)
        for name in DETAIL_FIELDS:
            widget = self._create_detail_widget(name)
            widget.setToolTip(FIELD_TOOLTIPS.get(name, name))
            self.detail_widgets[name] = widget
            form.addRow(self._form_label(name, FIELD_TOOLTIPS.get(name, name)), widget)
        layout.addWidget(group)
        layout.addStretch()
        scroll.setWidget(page)
        return scroll

    def _build_profiles_tab(self) -> QWidget:
        page = QWidget()
        page.setObjectName("settingsPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        group = QGroupBox("JSON-профили")
        group.setObjectName("settingsCard")
        form = QFormLayout(group)
        buttons = QHBoxLayout()
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
        form.addRow(
            self._form_label(
                "Действия",
                "Импортирует профиль из выбранного файла или экспортирует текущие настройки.",
            ),
            self._layout_widget(buttons),
        )

        layout.addWidget(group)
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
        layout.addWidget(self.logs, 1)
        return frame

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
            "VIDEO_CRF",
            "VIDEO_NVENC_CQ",
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
            if name in {"VIDEO_CRF", "VIDEO_NVENC_CQ", "INTERMEDIATE_VIDEO_CRF"}:
                spin.setRange(0, 51)
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
            "VIDEO_ENCODER": ["libx264", "h264_nvenc"],
            "INTERMEDIATE_VIDEO_ENCODER": ["libx264rgb", "libx264", "ffv1"],
            "VIDEO_PRESET": [
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
            "VIDEO_TUNE": [
                "animation",
                "",
                "film",
                "grain",
                "stillimage",
                "fastdecode",
                "zerolatency",
            ],
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
            "VIDEO_PIX_FMT": ["yuv420p", "yuv422p", "yuv444p"],
            "INTERMEDIATE_VIDEO_PIX_FMT": [
                "bgr24",
                "rgb24",
                "bgr0",
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
            combo.currentTextChanged.connect(
                lambda value, field=name: self._sync_config_from_widget(field, value)
            )
            return combo
        edit = QLineEdit()
        if name in {"ORIGINAL_VIDEO", "FINAL_VIDEO"}:
            edit.setReadOnly(True)
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
        if tooltip:
            label.setToolTip(tooltip)
        return label

    def _layout_widget(self, layout: QHBoxLayout) -> QWidget:
        widget = QWidget()
        widget.setObjectName("cardRow")
        widget.setLayout(layout)
        return widget

    def _populate_from_config(self, config: PipelineConfig) -> None:
        self.config = config
        input_blocker = QSignalBlocker(self.input_edit)
        output_blocker = QSignalBlocker(self.output_dir_edit)
        preset_blocker = QSignalBlocker(self.primary_preset_combo)
        denoise_blocker = QSignalBlocker(self.simple_denoise)
        interpolation_blocker = QSignalBlocker(self.simple_interpolation)
        encoder_blocker = QSignalBlocker(self.simple_encoder)
        self.input_edit.setText(config.ORIGINAL_VIDEO)
        self.output_dir_edit.setText(str(Path(config.FINAL_VIDEO).parent))
        self.primary_preset_combo.setCurrentText(self._matching_preset_name(config))
        self.simple_denoise.setChecked(config.ENABLE_DENOISE)
        self.simple_interpolation.setChecked(config.ENABLE_INTERPOLATION)
        self.simple_encoder.setCurrentText(config.VIDEO_ENCODER)
        del input_blocker
        del output_blocker
        del preset_blocker
        del denoise_blocker
        del interpolation_blocker
        del encoder_blocker
        self._update_final_video_from_primary_fields()

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
        values["ORIGINAL_VIDEO"] = self.input_edit.text().strip()
        values["FINAL_VIDEO"] = self.config.FINAL_VIDEO
        self.config = PipelineConfig(**values)
        return self.config

    def _sync_path_field(self, field: str, value: str) -> None:
        self._sync_config_from_widget(field, value)
        if field == "ORIGINAL_VIDEO":
            self._sync_output_dir_to_input_parent(value)
            self._update_final_video_from_primary_fields()

    def _sync_config_from_widget(self, field: str, value: Any) -> None:
        values = self.config.to_dict()
        values[field] = value
        self.config = PipelineConfig(**values)
        if field == "ORIGINAL_VIDEO" and self.input_edit.text() != str(value):
            self.input_edit.setText(str(value))
        elif field == "FINAL_VIDEO":
            self._set_detail_text("FINAL_VIDEO", str(value))

    def _set_detail_text(self, field: str, value: str) -> None:
        widget = self.detail_widgets.get(field)
        if isinstance(widget, QLineEdit) and widget.text() != value:
            widget.blockSignals(True)
            widget.setText(value)
            widget.blockSignals(False)

    def _output_dir_changed(self, _value: str) -> None:
        self._update_final_video_from_primary_fields()

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
        self._set_detail_text("ORIGINAL_VIDEO", self.config.ORIGINAL_VIDEO)
        self._set_detail_text("FINAL_VIDEO", self.config.FINAL_VIDEO)

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
        widget = self.detail_widgets.get(field)
        if isinstance(widget, QCheckBox):
            widget.setChecked(value)
        self._sync_config_from_widget(field, value)

    def _set_text_field(self, field: str, value: str) -> None:
        widget = self.detail_widgets.get(field)
        if isinstance(widget, QComboBox):
            widget.setCurrentText(value)
        self._sync_config_from_widget(field, value)

    def choose_input_video(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите входное видео",
            str(
                Path(self.input_edit.text()).parent
                if self.input_edit.text()
                else self.data_dir / "input_video"
            ),
            "Видео (*.mp4 *.mkv *.avi *.mov *.webm);;Все файлы (*)",
        )
        if path:
            self._apply_selected_input_video(Path(path))

    def _apply_selected_input_video(self, path: Path) -> None:
        input_blocker = QSignalBlocker(self.input_edit)
        self.input_edit.setText(str(path))
        del input_blocker
        self._sync_output_dir_to_input_parent(str(path))
        self._update_final_video_from_primary_fields()

    def choose_output_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "Выберите папку для итогового видео",
            self.output_dir_edit.text() or str(self.data_dir / "output_video"),
        )
        if path:
            self.output_dir_edit.setText(path)
            self._update_final_video_from_primary_fields()

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
        config = self._collect_config()
        errors = config.validate(require_input_exists=True)
        if errors:
            QMessageBox.warning(self, "Ошибки в настройках", "\n".join(errors))
            return
        output_path = Path(config.FINAL_VIDEO)
        if output_path.exists():
            result = QMessageBox.question(
                self,
                "Файл уже существует",
                f"Итоговый файл уже существует:\n{output_path}\n\nПерезаписать его?",
            )
            if result != QMessageBox.StandardButton.Yes:
                return
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
            return

        profile_path = self.profile_dir / "last_run_profile.json"
        config.save_json(profile_path)
        self._set_running_state(True)
        self._set_main_progress(0, "Запуск обработки")
        self._append_log("info", f"Запуск пайплайна с профилем: {profile_path}")

        configure_app_local_tools(self.project_root)
        try:
            program, arguments, workdir = self._pipeline_command(profile_path)
        except FileNotFoundError as error:
            self._append_log("critical", str(error))
            QMessageBox.critical(self, "Запуск невозможен", str(error))
            self._set_running_state(False)
            return

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
        if exit_status == QProcess.ExitStatus.NormalExit and exit_code == 0:
            self._append_log("info", "Процесс завершен успешно.")
            self._set_main_progress(100, "Обработка завершена")
            self.statusBar().showMessage("Обработка завершена")
        else:
            self._append_log("critical", f"Процесс завершился с кодом {exit_code}.")
            self.statusBar().showMessage("Обработка завершилась с ошибкой")
        self.process = None
        self._set_running_state(False)

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
            f"Извлечение кадров: {frame_percent}% / Общий прогресс: {overall_percent}%",
        )

    def _set_main_progress(self, value: int, status: str) -> None:
        safe_value = max(0, min(100, int(value)))
        self.progress.setValue(safe_value)
        if "Общий прогресс:" in status:
            display = status
        else:
            display = f"{status}: {safe_value}%"
        self.progress.setFormat(display)
        self.statusBar().showMessage(display)

    def toggle_logs_expanded(self, expanded: bool) -> None:
        if expanded:
            self.saved_splitter_sizes = self.splitter.sizes()
            self.header_widget.hide()
            self.primary_panel.hide()
            self.settings_area.hide()
            self.expand_logs_button.setText("Свернуть логи")
            self.splitter.setSizes([0, 1])
            self.logs.setFocus()
        else:
            self.header_widget.show()
            self.primary_panel.show()
            self.settings_area.show()
            self.expand_logs_button.setText("Развернуть логи")
            if self.saved_splitter_sizes:
                self.splitter.setSizes(self.saved_splitter_sizes)

    def process_error(self, error: QProcess.ProcessError) -> None:
        self._append_log("critical", f"Ошибка процесса: {error.name}")

    def _set_running_state(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.check_button.setEnabled(not running and self.env_thread is None)
        self.stop_button.setEnabled(running)
        self.statusBar().showMessage("Обработка выполняется" if running else "Готово")

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
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.raw_logs.append((level, f"[{timestamp}] {message}"))
        if len(self.raw_logs) > 20000:
            self.raw_logs = self.raw_logs[-20000:]
        if not self.logs_paused:
            self.render_logs()
        else:
            self.pending_log_render = True

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
