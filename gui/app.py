import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox, QFileDialog
from PySide6.QtCore import Qt

# Добавляем корневую директорию проекта в путь
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from gui.main_window import MainWindow
from gui.config import ConfigManager


def setup_application() -> QApplication:
    """Настройка QApplication с современными параметрами."""
    app = QApplication(sys.argv)
    app.setApplicationName("Anime Enhancement GUI")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("Olexasha")
    
    # Включаем поддержку HiDPI экранов
    app.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    return app


def check_dependencies() -> bool:
    """Проверка наличия основных зависимостей и структуры проекта."""
    try:
        main_py_path = project_root / "main.py"
        if not main_py_path.exists():
            QMessageBox.critical(
                None,
                "Ошибка",
                f"Файл main.py не найден в {project_root}.\n"
                "Убедитесь, что GUI запускается из корневой директории проекта."
            )
            return False

        settings_py_path = project_root / "src" / "config" / "settings.py"
        if not settings_py_path.exists():
            # Предлагаем пользователю выбрать settings.py вручную
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Critical)
            msg.setWindowTitle("Ошибка")
            msg.setText(f"Файл settings.py не найден в {settings_py_path}")
            msg.setInformativeText("Хотите выбрать файл вручную?")
            msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            result = msg.exec()

            if result == QMessageBox.Yes:
                file_path, _ = QFileDialog.getOpenFileName(
                    None,
                    "Выберите settings.py",
                    str(project_root),
                    "Python Files (*.py)"
                )
                if not file_path:
                    return False
                return True
            else:
                return False

        return True

    except Exception as e:
        QMessageBox.critical(
            None,
            "Ошибка",
            f"Ошибка при проверке зависимостей:\n{str(e)}"
        )
        return False


def main() -> int:
    """Главная функция запуска GUI приложения."""
    try:
        # Создаем приложение
        app = setup_application()
        
        # Проверяем зависимости
        if not check_dependencies():
            return 1
        
        # Инициализируем менеджер конфигурации
        config_manager = ConfigManager(project_root)
        
        # Создаем и показываем главное окно
        main_window = MainWindow(config_manager)
        main_window.show()
        
        # Запускаем приложение
        try:
            return app.exec()
        except Exception:
            QMessageBox.critical(
                None,
                "Критическая ошибка",
                "Произошла непредвиденная ошибка.\n"
                "Подробности смотрите в лог-файле."
            )
            return 1

    except Exception as e:
        QMessageBox.critical(
            None,
            "Критическая ошибка",
            f"Не удалось запустить GUI:\n{str(e)}"
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
