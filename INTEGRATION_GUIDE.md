# Руководство по интеграции GUI с main.py

## 🔧 Изменения в main.py

Для поддержки конфигурации из GUI в `main.py` были внесены следующие изменения:

### 1. Добавлены импорты

```python
import json
import sys
```

### 2. Добавлены функции для работы с GUI конфигурацией

```python
def load_gui_config() -> dict:
    """Загружает конфигурацию из GUI override файла."""
    gui_settings_path = os.getenv("GUI_SETTINGS")
    if gui_settings_path and os.path.exists(gui_settings_path):
        try:
            with open(gui_settings_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Ошибка загрузки GUI конфигурации: {e}")
    return {}


def apply_gui_config(config: dict) -> None:
    """Применяет конфигурацию из GUI к глобальным переменным."""
    if not config:
        return
    
    # Обновляем переменные в модуле settings
    import src.config.settings as settings_module
    
    for key, value in config.items():
        if hasattr(settings_module, key):
            setattr(settings_module, key, value)
            logger.debug(f"Применена настройка из GUI: {key} = {value}")
```

### 3. Интеграция в функцию main()

```python
async def main():
    """Основной процесс обработки видео."""
    start_time = datetime.now()
    print_header("запуск улучшения видео")

    try:
        # Загружаем конфигурацию из GUI
        gui_config = load_gui_config()
        if gui_config:
            apply_gui_config(gui_config)
            logger.info("Загружена конфигурация из GUI")
        
        # Остальной код остается без изменений...
```

## 📁 Структура файлов

После интеграции структура проекта должна выглядеть так:

```
anime_enhancement/
├── main.py                          # Обновлен для поддержки GUI
├── gui/                            # Новый модуль GUI
│   ├── app.py                      # Точка входа GUI
│   ├── main_window.py              # Главное окно
│   ├── settings_panel.py           # Панель настроек
│   ├── nn_panel.py                 # Панель нейронных сетей
│   ├── logs_panel.py               # Панель логов
│   ├── process_controller.py       # Контроллер процессов
│   ├── config.py                   # Менеджер конфигурации
│   ├── styles.qss                  # Стили интерфейса
│   └── utils/
│       └── logger.py               # Настройка логирования
├── tests/                          # Тесты GUI
│   ├── test_gui_config.py
│   └── test_gui_process_controller.py
├── requirements-gui.txt            # Зависимости для GUI
├── config.sample.json              # Пример конфигурации
├── run_gui.bat                     # Запуск на Windows
├── run_gui.sh                      # Запуск на Linux/macOS
├── README_GUI.md                   # Документация GUI
└── INTEGRATION_GUIDE.md            # Это руководство
```

## 🚀 Запуск GUI

### Windows
```cmd
run_gui.bat
```

### Linux/macOS
```bash
./run_gui.sh
```

### Ручной запуск
```bash
# Установка зависимостей
pip install -r requirements-gui.txt

# Запуск GUI
python gui/app.py
```

## ⚙️ Принцип работы

1. **GUI загружает настройки** из `src/config/settings.py`
2. **Пользователь редактирует** настройки через интерфейс
3. **GUI сохраняет изменения** в `settings_gui_override.json`
4. **При запуске main.py** через GUI:
   - Устанавливается переменная окружения `GUI_SETTINGS`
   - `main.py` загружает конфигурацию из JSON файла
   - Применяет настройки к модулю `settings`
5. **Обработка видео** происходит с новыми настройками

## 🔄 Откат изменений

Если нужно откатить изменения:

1. **Удалите файл** `settings_gui_override.json`
2. **Перезапустите GUI** - настройки вернутся к умолчанию
3. **Или используйте кнопку** "Reset to Defaults" в GUI

## 🧪 Тестирование

Запуск тестов:

```bash
# Все тесты GUI
python -m pytest tests/ -v

# Тесты конфигурации
python -m pytest tests/test_gui_config.py -v

# Тесты контроллера процессов
python -m pytest tests/test_gui_process_controller.py -v
```

## 🐛 Устранение неполадок

### GUI не запускается
- Проверьте установку PySide6: `pip list | grep PySide6`
- Убедитесь, что запускаете из корневой директории проекта
- Проверьте наличие файлов `main.py` и `src/config/settings.py`

### Процесс не запускается
- Проверьте путь к входному видео
- Убедитесь, что папки для выходных файлов существуют
- Проверьте свободное место на диске (минимум 10 ГБ)

### Ошибки конфигурации
- Удалите `settings_gui_override.json` для сброса к умолчанию
- Проверьте права доступа к файлам
- Убедитесь, что `settings.py` не поврежден

## 📝 Логирование

Логи GUI сохраняются в папке `logs/` с именем файла `gui_YYYYMMDD.log`.

## 🔧 Кастомизация

### Добавление новых настроек

1. **Добавьте поле** в `settings_panel.py` или `nn_panel.py`
2. **Обновите методы** `get_settings()` и `load_settings()`
3. **Добавьте переменную** в `src/config/settings.py`
4. **Обновите** `config.sample.json`

### Изменение стилей

Отредактируйте файл `gui/styles.qss` для изменения внешнего вида.

### Добавление новых панелей

1. **Создайте новый файл** в папке `gui/`
2. **Наследуйтесь** от `QWidget`
3. **Добавьте панель** в `main_window.py`
4. **Обновите навигацию** в sidebar

## 📋 TODO для дальнейшей разработки

- [ ] Добавить поддержку профилей настроек
- [ ] Реализовать предварительный просмотр кадров
- [ ] Добавить мониторинг GPU (pynvml)
- [ ] Создать мастер настройки для новых пользователей
- [ ] Добавить поддержку пакетной обработки
- [ ] Реализовать плагинную архитектуру для новых нейронных сетей
- [ ] Добавить поддержку темной темы
- [ ] Создать систему уведомлений
- [ ] Добавить поддержку горячих клавиш

## 🤝 Поддержка

При возникновении проблем:
1. Проверьте логи в папке `logs/`
2. Убедитесь, что все зависимости установлены
3. Проверьте совместимость версий Python и PySide6
4. Создайте issue в репозитории проекта

---

**Примечание**: Этот GUI является MVP (Minimum Viable Product) и может требовать доработки для полной интеграции с вашим проектом.
