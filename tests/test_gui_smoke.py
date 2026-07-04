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
    assert "ORIGINAL_VIDEO" not in DETAIL_FIELDS
    assert "FINAL_VIDEO" not in DETAIL_FIELDS
    assert "ORIGINAL_VIDEO" not in window.detail_widgets
    assert "FINAL_VIDEO" not in window.detail_widgets
    assert (
        window.detail_labels["INTERMEDIATE_VIDEO_PIX_FMT"].text()
        == "Формат пикселей short-видео"
    )
    assert window.detail_labels["FRAMES_MULTIPLY_FACTOR"].text() == "Множитель FPS"
    assert all(
        window.detail_labels[field].text() == FIELD_LABELS[field]
        for field in DETAIL_FIELDS
    )
    assert all(window.detail_labels[field].text() != field for field in DETAIL_FIELDS)
    assert window.primary_preset_combo.count() > 0
    assert window.queue_table.columnCount() == 6
    assert window.queue_table.rowCount() == 0
    assert window.start_button.text() == "Запустить очередь"
    assert not window.start_button.isEnabled()
    window.close()


def test_gui_can_export_and_import_profile(monkeypatch, tmp_path: Path):
    from PySide6.QtWidgets import QApplication

    from gui import main_window
    from gui.main_window import MainWindow

    _app = QApplication.instance() or QApplication([])
    window = MainWindow(Path(__file__).resolve().parents[1])
    profile = tmp_path / "gui_profile.json"
    output_dir = tmp_path / "result"
    output_dir.mkdir()
    input_video = tmp_path / "input.mp4"

    window.output_dir_edit.setText(str(output_dir))
    window._add_video_paths_to_queue([input_video])
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
    assert len(window.queue_items) == 1
    assert window.queue_items[0].output_path == expected_final
    assert window.queue_table.item(0, 2).text() == expected_final.name
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


def test_gui_preset_change_keeps_queue(tmp_path: Path):
    from PySide6.QtWidgets import QApplication

    from gui.main_window import PRESETS, MainWindow

    _app = QApplication.instance() or QApplication([])
    window = MainWindow(Path(__file__).resolve().parents[1])
    video = tmp_path / "episode.mkv"
    window._add_video_paths_to_queue([video])

    preset_name = list(PRESETS.keys())[-1]
    window.apply_selected_preset(preset_name)

    assert len(window.queue_items) == 1
    assert window.queue_items[0].input_path == video
    assert window.primary_preset_combo.currentText()
    window.close()


def test_gui_add_video_creates_queue_item_and_output_path(tmp_path: Path):
    from PySide6.QtWidgets import QApplication

    from gui.main_window import MainWindow

    _app = QApplication.instance() or QApplication([])
    window = MainWindow(Path(__file__).resolve().parents[1])
    input_video = tmp_path / "episode 01.mkv"
    output_dir = tmp_path / "out"

    window.output_dir_edit.setText(str(output_dir))
    window._add_video_paths_to_queue([input_video])

    expected_final = output_dir / "episode 01_enhanced.mp4"
    assert len(window.queue_items) == 1
    assert window.queue_items[0].input_path == input_video
    assert window.queue_items[0].output_path == expected_final
    assert window.queue_items[0].status == "Ожидает"
    assert window.queue_items[0].progress == 0
    assert window.queue_table.item(0, 1).text() == input_video.name
    assert window.queue_table.item(0, 2).text() == expected_final.name
    assert window.start_button.isEnabled()
    window.close()


def test_gui_choose_input_video_adds_to_queue(monkeypatch, tmp_path: Path):
    from PySide6.QtWidgets import QApplication

    from gui import main_window
    from gui.main_window import MainWindow

    _app = QApplication.instance() or QApplication([])
    window = MainWindow(Path(__file__).resolve().parents[1])
    input_video = tmp_path / "Naruto" / "episode 02.mkv"
    input_video.parent.mkdir()
    output_dir = tmp_path / "result"
    window.output_dir_edit.setText(str(output_dir))

    monkeypatch.setattr(
        main_window.QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(input_video), "Видео (*.mkv)"),
    )

    window.choose_input_video()

    expected_final = output_dir / "episode 02_enhanced.mp4"
    assert len(window.queue_items) == 1
    assert window.queue_items[0].input_path == input_video
    assert window.queue_items[0].output_path == expected_final
    assert window.queue_table.rowCount() == 1
    window.close()


def test_gui_choose_queue_videos_adds_multiple_in_order(monkeypatch, tmp_path: Path):
    from PySide6.QtWidgets import QApplication

    from gui import main_window
    from gui.main_window import MainWindow

    _app = QApplication.instance() or QApplication([])
    window = MainWindow(Path(__file__).resolve().parents[1])
    videos = [tmp_path / "episode 01.mkv", tmp_path / "episode 02.mkv"]

    monkeypatch.setattr(
        main_window.QFileDialog,
        "getOpenFileNames",
        lambda *args, **kwargs: ([str(video) for video in videos], "Видео (*.mkv)"),
    )

    window.choose_queue_videos()

    assert [item.input_path for item in window.queue_items] == videos
    assert [window.queue_table.item(row, 1).text() for row in range(2)] == [
        "episode 01.mkv",
        "episode 02.mkv",
    ]
    window.close()


def test_gui_output_dir_change_updates_pending_queue_outputs(tmp_path: Path):
    from PySide6.QtWidgets import QApplication

    from gui.main_window import MainWindow

    _app = QApplication.instance() or QApplication([])
    window = MainWindow(Path(__file__).resolve().parents[1])
    old_dir = tmp_path / "old"
    new_dir = tmp_path / "new"
    video = tmp_path / "episode 03.mp4"

    window.output_dir_edit.setText(str(old_dir))
    window._add_video_paths_to_queue([video])
    window.output_dir_edit.setText(str(new_dir))

    expected_final = new_dir / "episode 03_enhanced.mp4"
    assert window.queue_items[0].output_path == expected_final
    assert window.queue_table.item(0, 2).text() == expected_final.name
    window.close()


def test_gui_main_progress_uses_pipeline_markers_not_any_percent():
    from PySide6.QtWidgets import QApplication

    from gui.main_window import MainWindow

    _app = QApplication.instance() or QApplication([])
    window = MainWindow(Path(__file__).resolve().parents[1])

    window._handle_process_line("__GUI_PROGRESS__|30|Начало ИИ-обработки")
    assert window.progress.value() == 30
    assert "Начало ИИ-обработки" in window.progress_detail_label.text()

    window._handle_process_line("[INFO] Внутренний этап: 99%")
    assert window.progress.value() == 30

    window._handle_process_line("[INFO] Извлечение фреймов: 500/1000 (50%)")
    assert window.progress.value() == 30
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
    assert window._detect_level("[10.06.2026 10:00:00] ERROR: ffmpeg failed") == "error"
    window.close()


def test_gui_logs_can_expand_and_collapse():
    from PySide6.QtWidgets import QApplication

    from gui.main_window import MainWindow

    _app = QApplication.instance() or QApplication([])
    window = MainWindow(Path(__file__).resolve().parents[1])

    assert window.logs.maximumHeight() == window.compact_log_height

    window.toggle_logs_expanded(True)
    assert window.header_widget.isHidden()
    assert window.primary_panel.isHidden()
    assert window.settings_area.isHidden()
    assert window.expand_logs_button.text() == "Свернуть логи"
    assert window.logs.maximumHeight() > window.compact_log_height

    window.toggle_logs_expanded(False)
    assert not window.header_widget.isHidden()
    assert not window.primary_panel.isHidden()
    assert not window.settings_area.isHidden()
    assert window.expand_logs_button.text() == "Развернуть логи"
    assert window.logs.maximumHeight() == window.compact_log_height
    window.close()


def test_gui_progress_display_removes_duplicate_overall_text():
    from PySide6.QtWidgets import QApplication

    from gui.main_window import MainWindow

    _app = QApplication.instance() or QApplication([])
    window = MainWindow(Path(__file__).resolve().parents[1])

    window._handle_process_line(
        "__GUI_PROGRESS__|37|Этап: RIFE; Батчи: 15-16 из 51; "
        "Прогресс этапа: 42%; Прошло: 01:48:12; Осталось: ~02:35:40; "
        "Скорость: 8.9 FPS; Общий прогресс: 37%"
    )

    assert window.progress.format() == "37%"
    assert window.progress_status_label.text() == "Обработка · RIFE · батчи 15-16 из 51"
    details = window.progress_detail_label.text()
    assert details.count("Общий прогресс") == 1
    assert "Локально: 42%" in details
    assert "8.9 FPS" in details
    assert "Скорость:" not in details
    window.close()


def test_gui_done_progress_uses_single_completion_line():
    from PySide6.QtWidgets import QApplication

    from gui.main_window import MainWindow

    _app = QApplication.instance() or QApplication([])
    window = MainWindow(Path(__file__).resolve().parents[1])

    window._set_main_progress(
        100, "ГОТОВО: видео обработано за 05:55:50; Общий прогресс: 100%"
    )

    assert window.progress.format() == "100%"
    assert (
        window.progress_status_label.text() == "Готово · видео обработано за 05:55:50"
    )
    assert window.progress_detail_label.isHidden()
    window.close()


def test_gui_video_queue_respects_limit_and_output_paths(tmp_path: Path):
    from PySide6.QtWidgets import QApplication

    from gui.main_window import MAX_QUEUE_VIDEOS, MainWindow

    _app = QApplication.instance() or QApplication([])
    window = MainWindow(Path(__file__).resolve().parents[1])
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    window.output_dir_edit.setText(str(output_dir))
    videos = [
        tmp_path / f"episode_{index}.mkv" for index in range(MAX_QUEUE_VIDEOS + 1)
    ]

    window._add_video_paths_to_queue(videos)

    assert len(window.queue_items) == MAX_QUEUE_VIDEOS
    assert window.queue_table.rowCount() == MAX_QUEUE_VIDEOS
    assert window.start_button.text() == "Запустить очередь"
    assert window.start_button.isEnabled()
    config = window._config_for_video(videos[0])
    assert config.ORIGINAL_VIDEO == str(videos[0])
    assert config.FINAL_VIDEO == str(output_dir / "episode_0_enhanced.mp4")
    window.close()


def test_gui_video_queue_remove_clear_and_reorder(tmp_path: Path):
    from PySide6.QtWidgets import QApplication

    from gui.main_window import MainWindow

    _app = QApplication.instance() or QApplication([])
    window = MainWindow(Path(__file__).resolve().parents[1])
    videos = [tmp_path / f"episode_{index}.mkv" for index in range(3)]

    window._add_video_paths_to_queue(videos)
    assert [item.input_path for item in window.queue_items] == videos
    assert window.queue_table.rowCount() == 3

    window.queue_table.selectRow(2)
    window.move_selected_queue_item_up()
    assert [item.input_path for item in window.queue_items] == [
        videos[0],
        videos[2],
        videos[1],
    ]

    window.remove_selected_queue_item()
    assert [item.input_path for item in window.queue_items] == [videos[0], videos[1]]

    window.clear_queue()
    assert window.queue_items == []
    assert window.queue_table.rowCount() == 0
    assert not window.start_button.isEnabled()
    window.close()


def test_gui_queue_action_buttons_fit_row(tmp_path: Path):
    from PySide6.QtWidgets import QApplication

    from gui.main_window import MainWindow

    _app = QApplication.instance() or QApplication([])
    window = MainWindow(Path(__file__).resolve().parents[1])
    videos = [tmp_path / "episode_01.mkv", tmp_path / "episode_02.mkv"]

    window._add_video_paths_to_queue(videos)

    assert window.queue_table.columnWidth(5) >= 112
    assert window.queue_table.rowHeight(0) >= 38
    actions = window.queue_table.cellWidget(0, 5)
    buttons = actions.findChildren(type(window.add_queue_button))
    assert len(buttons) == 3
    assert all(button.width() >= 28 and button.height() >= 26 for button in buttons)
    window.close()


def test_gui_detail_combo_values_have_readable_minimum_width():
    from PySide6.QtWidgets import QApplication

    from gui.main_window import MainWindow

    _app = QApplication.instance() or QApplication([])
    window = MainWindow(Path(__file__).resolve().parents[1])
    encoder = window.detail_widgets["INTERMEDIATE_VIDEO_ENCODER"]
    pix_fmt = window.detail_widgets["INTERMEDIATE_VIDEO_PIX_FMT"]
    encoder_label = window.detail_labels["INTERMEDIATE_VIDEO_ENCODER"]

    assert encoder.minimumWidth() >= 190
    assert pix_fmt.minimumWidth() >= 190
    assert encoder_label.maximumWidth() <= 230
    assert encoder_label.wordWrap()
    window.close()


def test_gui_video_queue_starts_next_item_after_success(monkeypatch, tmp_path: Path):
    from PySide6.QtWidgets import QApplication

    from gui import main_window
    from gui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow(Path(__file__).resolve().parents[1])
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    videos = [tmp_path / "episode_01.mkv", tmp_path / "episode_02.mkv"]
    for video in videos:
        video.write_text("stub", encoding="utf-8")
    window.output_dir_edit.setText(str(output_dir))
    window._add_video_paths_to_queue(videos)
    monkeypatch.setattr(main_window, "check_environment", lambda *_args: [])
    starts = []

    def fake_start_config_process(config, _profile_path, start_status):
        starts.append((config.ORIGINAL_VIDEO, start_status))
        window.process = object()
        return True

    monkeypatch.setattr(window, "_start_config_process", fake_start_config_process)

    window.start_queue()
    assert starts == [(str(videos[0]), "Этап: запуск; Файл: episode_01.mkv")]
    assert window.queue_items[0].status == "В обработке"

    window.process_finished(0, main_window.QProcess.ExitStatus.NormalExit)
    app.processEvents()
    assert starts == [
        (str(videos[0]), "Этап: запуск; Файл: episode_01.mkv"),
        (str(videos[1]), "Этап: запуск; Файл: episode_02.mkv"),
    ]
    assert window.queue_items[0].status == "Готово"
    assert window.queue_items[0].progress == 100
    assert window.queue_items[1].status == "В обработке"

    window.process_finished(0, main_window.QProcess.ExitStatus.NormalExit)
    app.processEvents()
    assert not window.queue_active
    assert [item.status for item in window.queue_items] == ["Готово", "Готово"]
    window.close()


def test_gui_video_queue_aggregates_current_item_progress(monkeypatch, tmp_path: Path):
    from PySide6.QtWidgets import QApplication

    from gui import main_window
    from gui.main_window import MainWindow

    _app = QApplication.instance() or QApplication([])
    window = MainWindow(Path(__file__).resolve().parents[1])
    videos = [tmp_path / "episode_01.mkv", tmp_path / "episode_02.mkv"]
    for video in videos:
        video.write_text("stub", encoding="utf-8")
    window._add_video_paths_to_queue(videos)
    monkeypatch.setattr(main_window, "check_environment", lambda *_args: [])

    def fake_start_config_process(_config, _profile_path, start_status):
        window.process = object()
        window._set_main_progress(0, start_status)
        return True

    monkeypatch.setattr(window, "_start_config_process", fake_start_config_process)

    window.start_queue()
    window._handle_process_line("__GUI_PROGRESS__|50|Этап: RIFE; Прогресс этапа: 50%")

    assert window.progress.value() == 25
    assert window.queue_items[0].progress == 50
    assert window.queue_items[1].progress == 0
    assert "Общий прогресс: 25%" in window.progress_detail_label.text()
    assert "Текущее видео: 50%" in window.progress_detail_label.text()
    window.close()


def test_gui_video_queue_stop_prevents_next_item(monkeypatch, tmp_path: Path):
    from PySide6.QtWidgets import QApplication

    from gui import main_window
    from gui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow(Path(__file__).resolve().parents[1])
    videos = [tmp_path / "episode_01.mkv", tmp_path / "episode_02.mkv"]
    for video in videos:
        video.write_text("stub", encoding="utf-8")
    window._add_video_paths_to_queue(videos)
    monkeypatch.setattr(main_window, "check_environment", lambda *_args: [])
    starts = []

    class FakeProcess:
        def terminate(self):
            pass

    def fake_start_config_process(config, _profile_path, _start_status):
        starts.append(config.ORIGINAL_VIDEO)
        window.process = FakeProcess()
        return True

    monkeypatch.setattr(window, "_start_config_process", fake_start_config_process)

    window.start_queue()
    window.stop_process()
    window.process_finished(0, main_window.QProcess.ExitStatus.NormalExit)
    app.processEvents()

    assert starts == [str(videos[0])]
    assert not window.queue_active
    assert [item.status for item in window.queue_items] == [
        "Остановлено",
        "Остановлено",
    ]
    window.close()
