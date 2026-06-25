import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_gui_import_and_window_smoke():
    from PySide6.QtWidgets import QApplication

    from gui.main_window import DETAIL_FIELDS, MainWindow
    from src.config.pipeline_config import FIELD_LABELS

    _app = QApplication.instance() or QApplication([])
    window = MainWindow(Path(__file__).resolve().parents[1])

    assert window.windowTitle() == "Anime Enhancement"
    assert window.detail_widgets["FINAL_VIDEO"] is not None
    assert window.detail_labels["ORIGINAL_VIDEO"].text() == "Исходное видео"
    assert (
        window.detail_labels["INTERMEDIATE_VIDEO_PIX_FMT"].text()
        == "Формат пикселей short-видео"
    )
    assert window.detail_labels["FRAMES_MULTIPLY_FACTOR"].text() == "Множитель FPS"
    assert all(
        window.detail_labels[field].text() == FIELD_LABELS[field]
        for field in DETAIL_FIELDS
    )
    assert all(
        window.detail_labels[field].text() != field for field in DETAIL_FIELDS
    )
    assert window.primary_preset_combo.count() > 0
    window.close()


def test_gui_can_export_and_import_profile(monkeypatch, tmp_path: Path):
    from PySide6.QtWidgets import QApplication

    from gui import main_window
    from gui.main_window import MainWindow

    _app = QApplication.instance() or QApplication([])
    window = MainWindow(Path(__file__).resolve().parents[1])
    profile = tmp_path / "gui_profile.json"
    output_dir = tmp_path / "result"

    window.input_edit.setText(str(tmp_path / "input.mp4"))
    window.output_dir_edit.setText(str(output_dir))
    monkeypatch.setattr(
        main_window.QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(profile), "JSON (*.json)"),
    )
    window.export_profile_clicked()

    assert profile.exists()

    window.output_dir_edit.setText(str(tmp_path / "changed"))
    monkeypatch.setattr(
        main_window.QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(profile), "JSON (*.json)"),
    )
    window.import_profile_clicked()

    expected_final = output_dir / "input_enhanced.mp4"
    assert window.output_dir_edit.text() == str(output_dir)
    assert window.final_path_label.text() == str(expected_final)
    assert window.detail_widgets["FINAL_VIDEO"].text() == str(expected_final)
    window.close()


def test_gui_max_quality_enables_temporal_tta():
    from PySide6.QtWidgets import QApplication, QCheckBox

    from gui.main_window import MainWindow

    _app = QApplication.instance() or QApplication([])
    window = MainWindow(Path(__file__).resolve().parents[1])
    widget = window.detail_widgets["ENABLE_TEMPORAL_TTA_MODE"]

    assert isinstance(widget, QCheckBox)
    assert widget.isEnabled()
    assert widget.isChecked()
    window.close()


def test_gui_input_selection_sets_output_dir_to_input_dir(tmp_path: Path):
    from PySide6.QtWidgets import QApplication

    from gui.main_window import MainWindow

    _app = QApplication.instance() or QApplication([])
    window = MainWindow(Path(__file__).resolve().parents[1])
    input_video = tmp_path / "episode 01.mkv"

    window._apply_selected_input_video(input_video)

    expected_final = tmp_path / "episode 01_enhanced.mp4"
    assert window.input_edit.text() == str(input_video)
    assert window.output_dir_edit.text() == str(tmp_path)
    assert window.final_path_label.text() == str(expected_final)
    assert window.detail_widgets["FINAL_VIDEO"].text() == str(expected_final)
    window.close()


def test_gui_choose_input_video_updates_output_dir_after_open(
    monkeypatch, tmp_path: Path
):
    from PySide6.QtWidgets import QApplication

    from gui import main_window
    from gui.main_window import MainWindow

    _app = QApplication.instance() or QApplication([])
    window = MainWindow(Path(__file__).resolve().parents[1])
    input_video = tmp_path / "Naruto" / "episode 02.mkv"
    input_video.parent.mkdir()
    window.output_dir_edit.setText(str(tmp_path / "old-result-dir"))

    monkeypatch.setattr(
        main_window.QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(input_video), "Видео (*.mkv)"),
    )

    window.choose_input_video()

    expected_final = input_video.parent / "episode 02_enhanced.mp4"
    assert window.input_edit.text() == str(input_video)
    assert window.output_dir_edit.text() == str(input_video.parent)
    assert window.final_path_label.text() == str(expected_final)
    assert window.detail_widgets["FINAL_VIDEO"].text() == str(expected_final)
    window.close()


def test_gui_input_text_change_updates_output_dir(tmp_path: Path):
    from PySide6.QtWidgets import QApplication

    from gui.main_window import MainWindow

    _app = QApplication.instance() or QApplication([])
    window = MainWindow(Path(__file__).resolve().parents[1])
    input_video = tmp_path / "same-folder" / "episode 03.mp4"
    input_video.parent.mkdir()
    window.output_dir_edit.setText(str(tmp_path / "old"))

    window.input_edit.setText(str(input_video))

    expected_final = input_video.parent / "episode 03_enhanced.mp4"
    assert window.output_dir_edit.text() == str(input_video.parent)
    assert window.final_path_label.text() == str(expected_final)
    window.close()


def test_gui_main_progress_uses_pipeline_markers_not_any_percent():
    from PySide6.QtWidgets import QApplication

    from gui.main_window import MainWindow

    _app = QApplication.instance() or QApplication([])
    window = MainWindow(Path(__file__).resolve().parents[1])

    window._handle_process_line("__GUI_PROGRESS__|30|Начало ИИ-обработки")
    assert window.progress.value() == 30
    assert "Начало ИИ-обработки" in window.progress.format()

    window._handle_process_line("[INFO] Внутренний этап: 99%")
    assert window.progress.value() == 30

    window._handle_process_line("[INFO] Извлечение фреймов: 500/1000 (50%)")
    assert window.progress.value() == 6
    window.close()


def test_gui_does_not_mark_ffmpeg_loglevel_argument_as_error():
    from PySide6.QtWidgets import QApplication

    from gui.main_window import MainWindow

    _app = QApplication.instance() or QApplication([])
    window = MainWindow(Path(__file__).resolve().parents[1])

    assert (
        window._detect_level(
            "[10.06.2026 10:00:00] INFO: Запуск FFmpeg: ffmpeg -loglevel error -i input output"
        )
        == "info"
    )
    assert (
        window._detect_level("[10.06.2026 10:00:00] ERROR: ffmpeg failed")
        == "error"
    )
    window.close()


def test_gui_logs_can_expand_and_collapse():
    from PySide6.QtWidgets import QApplication

    from gui.main_window import MainWindow

    _app = QApplication.instance() or QApplication([])
    window = MainWindow(Path(__file__).resolve().parents[1])

    window.toggle_logs_expanded(True)
    assert window.header_widget.isHidden()
    assert window.primary_panel.isHidden()
    assert window.settings_area.isHidden()
    assert window.expand_logs_button.text() == "Свернуть логи"

    window.toggle_logs_expanded(False)
    assert not window.header_widget.isHidden()
    assert not window.primary_panel.isHidden()
    assert not window.settings_area.isHidden()
    assert window.expand_logs_button.text() == "Развернуть логи"
    window.close()
