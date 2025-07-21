import logging

from src.config.settings import LOGS_DIR
from src.files.file_actions import create_dir


class LogColors:
    GREY = "\x1b[38;20m"
    WHITE = "\x1b[97m"
    YELLOW = "\x1b[33;20m"
    RED = "\x1b[31;20m"
    BOLD_RED = "\x1b[31;1m"
    GREEN = "\x1b[32;20m"
    CYAN = "\x1b[36;20m"
    RESET = "\x1b[0m"


class CustomFormatter(logging.Formatter):
    """Кастомный форматтер с цветами для разных уровней логгирования"""

    SUCCESS_LEVEL = 25
    logging.addLevelName(SUCCESS_LEVEL, "SUCCESS")
    base_format = "[%(asctime)s] %(levelname)s: %(message)s"

    FORMATS = {
        logging.DEBUG: LogColors.GREEN + base_format + LogColors.RESET,
        logging.INFO: LogColors.WHITE + base_format + LogColors.RESET,
        SUCCESS_LEVEL: LogColors.CYAN + base_format + LogColors.RESET,
        logging.WARNING: LogColors.YELLOW + base_format + LogColors.RESET,
        logging.ERROR: LogColors.RED + base_format + LogColors.RESET,
        logging.CRITICAL: LogColors.BOLD_RED + base_format + LogColors.RESET,
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno, self.base_format)
        formatter = logging.Formatter(log_fmt, datefmt="%d.%m.%Y %H:%M:%S")
        return formatter.format(record)


class Logger:
    def __init__(
        self,
        name: str = "app",
        level: int = logging.INFO,
        log_file: str = "",
    ):
        self.logger = logging.getLogger(name)
        self.level = level
        self.logger.setLevel(level)
        self._add_success_method()

        # консольный обработчик
        self._setup_console_handler()

        # файловый обработчик, если указан файл
        if log_file:
            self._setup_file_handler(log_file)

    def _add_success_method(self):
        """Добавляем метод success к логгеру"""

        def success(self, msg, *args, **kwargs):
            if self.isEnabledFor(CustomFormatter.SUCCESS_LEVEL):
                self._log(CustomFormatter.SUCCESS_LEVEL, msg, args, **kwargs)

        logging.Logger.success = success

    def _remove_existing_handlers(self):
        """Удаляет существующие обработчики"""
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)

    def _setup_console_handler(self):
        """Настройка цветного вывода в консоль"""
        ch = logging.StreamHandler()
        ch.setLevel(self.level)
        ch.setFormatter(CustomFormatter())
        self.logger.addHandler(ch)

    def _setup_file_handler(self, log_file: str):
        """Настройка записи в файл (без цветов)"""
        from logging.handlers import RotatingFileHandler

        logs_dir = create_dir(LOGS_DIR, "logs")
        fh = RotatingFileHandler(
            f"{logs_dir}/{log_file}",
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        fh.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s (%(filename)s:%(lineno)d)",
            datefmt="%d-%m-%Y %H:%M:%S",
        )
        fh.setFormatter(file_formatter)
        self.logger.addHandler(fh)

    def get_logger(self):
        return self.logger


logger = Logger().get_logger()
