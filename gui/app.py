from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from src.config.runtime_paths import app_root, resource_path


def configure_text_output() -> None:
    """Нужен для frozen-режима, когда этот exe запускают как CLI с --config."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


configure_text_output()


def resolve_project_root() -> Path:
    return app_root()


def configure_windows_app_id() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "anime_enhancement.AnimeEnhancement"
        )
    except Exception:
        pass


PROJECT_ROOT = resolve_project_root()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from gui.main_window import MainWindow  # noqa: E402


def setup_application() -> QApplication:
    configure_windows_app_id()
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    app = QApplication(sys.argv)
    app.setApplicationName("Anime Enhancement")
    app.setApplicationVersion("2.0.0")
    app.setOrganizationName("anime_enhancement")
    try:
        app.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    except AttributeError:
        pass

    style_path = resource_path("gui/styles.qss")
    if not style_path.exists():
        style_path = Path(__file__).with_name("styles.qss")
    if style_path.exists():
        app.setStyleSheet(style_path.read_text(encoding="utf-8"))
    icon_path = resource_path("packaging/windows/assets/anime_enhancement.ico")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    return app


def main() -> int:
    if any(
        arg in sys.argv[1:]
        for arg in (
            "--config",
            "--check-environment",
            "--print-effective-config",
            "--dry-run",
        )
    ):
        from main import main as cli_main

        return cli_main(sys.argv[1:])

    app = setup_application()
    try:
        window = MainWindow(PROJECT_ROOT)
        if "--smoke-test" in sys.argv:
            window.close()
            return 0
        window.show()
        return app.exec()
    except Exception as error:
        QMessageBox.critical(
            None, "Критическая ошибка", f"Не удалось запустить GUI:\n{error}"
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
