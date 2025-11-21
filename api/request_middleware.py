# api/request_middleware.py
"""
Middleware для трейсинга HTTP запросов и автоматического логирования.

Этот модуль добавляет:
- Уникальный Request ID для каждого запроса
- Автоматическое логирование всех HTTP запросов
- Измерение времени выполнения запросов
- Добавление Request ID в заголовки ответов
"""

import logging
import time
import uuid

from flask import g, request


def generate_request_id():
    """
    Генерирует уникальный Request ID для трейсинга запроса.

    Returns:
        str: Уникальный идентификатор формата 'req_8a7b9c4d'

    Примеры:
        >>> generate_request_id()
        'req_a1b2c3d4'
        >>> generate_request_id()
        'req_e5f6g7h8'
    """
    # uuid.uuid4() создаёт случайный UUID (например, '550e8400-e29b-41d4-a716-446655440000')
    # .hex берёт только шестнадцатеричные цифры (без дефисов)
    # [:8] берёт первые 8 символов для краткости
    return f"req_{uuid.uuid4().hex[:8]}"


def setup_request_logging(app):
    """
    Настраивает middleware для автоматического логирования всех HTTP запросов.

    Args:
        app: Flask application instance

    Что делает:
        1. Перед запросом: генерирует Request ID, засекает время
        2. После запроса: логирует результат (статус, время выполнения)
    """

    @app.before_request
    def before_request():
        """
        Выполняется ПЕРЕД обработкой каждого HTTP запроса.

        Действия:
        - Генерирует Request ID
        - Сохраняет время начала запроса
        - Логирует входящий запрос
        """
        # Генерируем уникальный ID для этого запроса
        g.request_id = generate_request_id()

        # Засекаем время начала (в секундах с 1 января 1970 года)
        g.start_time = time.time()

        # Получаем IP адрес клиента
        # request.remote_addr — IP из TCP соединения
        # request.headers.get('X-Forwarded-For') — если запрос идёт через прокси/load balancer
        client_ip = request.headers.get("X-Forwarded-For", request.remote_addr)

        # Логируем входящий запрос
        app.logger.info(
            "Incoming request",
            extra={
                "request_id": g.request_id,
                "method": request.method,  # GET, POST, PUT и т.д.
                "path": request.path,  # /search, /sku/D011283 и т.д.
                "query_string": request.query_string.decode("utf-8"),
                # ?q=вино&max_price=3000
                "client_ip": client_ip,
                "user_agent": request.headers.get("User-Agent", "unknown"),
            },
        )

    @app.after_request
    def after_request(response):
        """
        Выполняется ПОСЛЕ обработки каждого HTTP запроса.

        Args:
            response: HTTP ответ от Flask

        Returns:
            response: Модифицированный HTTP ответ с добавленным заголовком X-Request-ID

        Действия:
        - Вычисляет время выполнения запроса
        - Логирует результат выполнения
        - Добавляет Request ID в заголовок ответа
        """
        # Вычисляем время выполнения запроса (в миллисекундах)
        if hasattr(g, "start_time"):
            duration_ms = (time.time() - g.start_time) * 1000  # секунды -> миллисекунды
        else:
            duration_ms = 0

        # Получаем Request ID (если он был создан)
        request_id = getattr(g, "request_id", "unknown")

        # Определяем уровень логирования в зависимости от статус кода
        if response.status_code >= 500:
            log_level = logging.ERROR  # 5xx — ошибки сервера
        elif response.status_code >= 400:
            log_level = logging.WARNING  # 4xx — ошибки клиента
        else:
            log_level = logging.INFO  # 2xx, 3xx — успешные запросы

        # Логируем результат выполнения запроса
        app.logger.log(
            log_level,
            "Request completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.path,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 2),
                "response_size_bytes": response.content_length or 0,
            },
        )

        # Добавляем Request ID в заголовок HTTP ответа
        # Теперь клиент может увидеть Request ID в HTTP заголовках!
        response.headers["X-Request-ID"] = request_id

        return response
