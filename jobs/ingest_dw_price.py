"""
Ежедневный импорт прайс-листов DW.
Запускается cron: пн-пт 12:10 Europe/Moscow

Issue: #82
"""

# Остальные импорты
import logging
import sys
from datetime import datetime
from pathlib import Path

from scripts.load_csv import main as load_csv_main

# Добавить корневую директорию проекта в sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


# ============================================================================
# Настройка логирования
# ============================================================================


def setup_logging():
    """
    Настроить логирование в файл и консоль.

    Формат: timestamp [LEVEL] message
    Файл: logs/import.log
    Консоль: только INFO и выше
    """
    # Создать папку logs/ если её нет
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    # Настроить логгер
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)  # Ловим всё

    # Удалить старые handlers (если есть)
    logger.handlers.clear()

    # Formatter (одинаковый для файла и консоли)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Handler 1: Файл (все уровни)
    file_handler = logging.FileHandler(log_dir / "import.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)  # Все уровни в файл
    logger.addHandler(file_handler)

    # Handler 2: Консоль (только INFO+)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)  # Только INFO и выше
    logger.addHandler(console_handler)

    return logger


# ============================================================================
# Обработка файлов
# ============================================================================


def process_file(file_path: Path, logger: logging.Logger) -> bool:
    """
    Обработать один файл.

    Args:
        file_path: Путь к файлу для импорта
        logger: Logger instance

    Returns:
        True если успешно, False если ошибка
    """
    try:
        logger.info(f"Processing: {file_path.name}")

        # Сохранить оригинальные аргументы
        original_argv = sys.argv.copy()

        # Подменить аргументы для load_csv
        if file_path.suffix.lower() in [".xlsx", ".xls", ".xlsm"]:
            sys.argv = ["load_csv.py", "--excel", str(file_path)]
        else:  # .csv
            sys.argv = ["load_csv.py", "--csv", str(file_path)]

        # Вызвать импорт
        load_csv_main()

        # Восстановить оригинальные аргументы
        sys.argv = original_argv

        logger.info(f"✅ Success: {file_path.name}")
        return True

    except Exception as e:
        logger.error(f"❌ Error processing {file_path.name}: {e}", exc_info=True)
        # Восстановить sys.argv даже при ошибке
        sys.argv = original_argv
        return False


def archive_file(file_path: Path, logger: logging.Logger) -> Path:
    """
    Переместить файл в архив.

    Структура архива: data/archive/YYYY-MM-DD/filename.xlsx

    Args:
        file_path: Путь к файлу
        logger: Logger instance

    Returns:
        Путь к архивированному файлу

    Example:
        data/inbox/Price_2025_11_02.xlsx
        -> data/archive/2025-11-02/Price_2025_11_02.xlsx
    """
    # TODO 1: Создать путь к папке архива (data/archive/YYYY-MM-DD/)
    today = datetime.now().strftime("%Y-%m-%d")
    archive_dir = Path("data/archive") / today

    # TODO 2: Создать папку архива (если её нет)
    archive_dir.mkdir(parents=True, exist_ok=True)

    # TODO 3: Создать путь к архивированному файлу
    archived_path = archive_dir / file_path.name

    # TODO 4: Переместить файл
    file_path.rename(archived_path)

    # TODO 5: Залогировать успех
    logger.info(f"📦 Archived: {file_path.name} -> {archived_path}")

    return archived_path


# ============================================================================
# Главная функция
# ============================================================================


def run_daily_import(logger: logging.Logger):
    """
    Главная функция: обработка всех файлов из inbox.

    Процесс:
    1. Найти все файлы в data/inbox/
    2. Отфильтровать только .xlsx, .xls, .csv
    3. Обработать каждый файл
    4. Архивировать успешные
    5. Залогировать итоги
    """
    inbox_dir = Path("data/inbox")

    # TODO 1: Проверить, что папка inbox существует
    if not inbox_dir.exists():
        inbox_dir.mkdir(parents=True, exist_ok=True)
        logger.warning(f"Created inbox directory: {inbox_dir}")

    # TODO 2: Найти все файлы в inbox
    # Найти все элементы
    all_items = inbox_dir.glob("*")
    # Только файлы (не папки)
    all_files = [f for f in all_items if f.is_file()]

    # Фильтр по расширению
    valid_extensions = {".xlsx", ".xls", ".xlsm", ".csv"}
    files = [f for f in all_files if f.suffix.lower() in valid_extensions]
    files = sorted(files)  # Сортировка для предсказуемого порядка

    # TODO 3: Если файлов нет - залогировать и выйти
    if not files:
        logger.info("No files found in inbox")
        return

    logger.info(f"Found {len(files)} file(s) to process")

    # Статистика
    success_count = 0
    error_count = 0

    # TODO 4: Обработать каждый файл
    for file_path in files:
        # TODO 4.1: Вызвать process_file()
        if process_file(file_path, logger):
            # TODO 4.2: Если успешно - архивировать и увеличить счётчик
            archive_file(file_path, logger)
            success_count += 1
        else:
            # TODO 4.3: Если ошибка - увеличить error_count
            # Файл остаётся в inbox для повторной обработки
            error_count += 1

    # TODO 5: Залогировать итоговую статистику
    logger.info(f"Import completed: {success_count} success, {error_count} errors")

    # TODO 6: Если есть ошибки - залогировать критическое предупреждение
    if error_count > 0:
        logger.critical(f"⚠️ ALERT: {error_count} file(s) failed to import!")


# ============================================================================
# Entry point
# ============================================================================

if __name__ == "__main__":
    logger = setup_logging()
    logger.info("=== Starting daily import job ===")

    try:
        run_daily_import(logger)  # Передаём logger как параметр
        logger.info("=== Daily import job finished ===")
    except Exception as e:
        logger.error(f"Daily import job failed: {e}", exc_info=True)
        sys.exit(1)
