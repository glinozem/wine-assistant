# api/logging_config.py
"""
Конфигурация структурированного JSON логирования для Wine Assistant API.

Этот модуль настраивает:
- JSON форматирование логов
- Уровни логирования (DEBUG/INFO/WARNING/ERROR)
- Структуру лог-сообщений
"""

import logging
import os

from pythonjsonlogger import jsonlogger


def setup_logging(app):
    """
    Настраивает JSON логирование для Flask приложения.

    Args:
        app: Flask application instance
    """
    # Получаем уровень логирования из переменной окружения (по умолчанию INFO)
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    # Преобразуем текст в константу Python (например, "INFO" -> logging.INFO)
    numeric_level = getattr(logging, log_level, logging.INFO)

    # Создаём JSON форматтер с нужными полями
    class CustomJsonFormatter(jsonlogger.JsonFormatter):
        """
        Кастомный форматтер для добавления дополнительных полей в JSON логи.
        """

        def add_fields(self, log_record, record, message_dict):
            """
            Добавляет стандартные поля в каждое лог-сообщение.

            Args:
                log_record: dict — итоговый JSON объект
                record: LogRecord — оригинальный Python лог
                message_dict: dict — дополнительные поля
            """
            super(CustomJsonFormatter, self).add_fields(log_record, record,
                                                        message_dict)

            # Добавляем обязательные поля
            log_record['timestamp'] = record.created  # Unix timestamp
            log_record['level'] = record.levelname  # DEBUG/INFO/WARNING/ERROR
            log_record[
                'logger'] = record.name  # Имя логгера (например, 'api.app')
            log_record[
                'module'] = record.module  # Имя модуля (например, 'app')
            log_record['function'] = record.funcName  # Имя функции

            # Если есть информация об исключении, добавляем её
            if record.exc_info:
                log_record['exception'] = self.formatException(record.exc_info)

    # Создаём handler (обработчик), который будет выводить логи в консоль
    console_handler = logging.StreamHandler()
    console_handler.setLevel(numeric_level)

    # Устанавливаем JSON форматтер для handler'а
    formatter = CustomJsonFormatter(
        '%(timestamp)s %(level)s %(name)s %(message)s'
    )
    console_handler.setFormatter(formatter)

    # Настраиваем корневой логгер приложения
    app.logger.setLevel(numeric_level)
    app.logger.handlers = []  # Удаляем старые handlers
    app.logger.addHandler(console_handler)

    # Отключаем дублирование логов от Werkzeug (Flask HTTP server)
    logging.getLogger('werkzeug').setLevel(logging.WARNING)

    # Логируем успешную инициализацию
    app.logger.info(
        "JSON logging initialized",
        extra={
            "log_level": log_level,
            "version": os.getenv("APP_VERSION", "unknown")
        }
    )
