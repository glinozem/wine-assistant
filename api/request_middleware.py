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

        # Засекаем время начала (высокоточный таймер)
        g.start_time = time.perf_counter()

        # Получаем IP адрес клиента
        client_ip = request.headers.get("X-Forwarded-For", request.remote_addr)

        # Логируем входящий запрос
        app.logger.info(
            "Incoming request",
            extra={
                "request_id": g.request_id,
                "method": request.method,  # GET, POST, PUT и т.д.
                "path": request.path,  # /search, /sku/D011283 и т.д.
                "query_string": request.query_string.decode("utf-8"),
                "client_ip": client_ip,
                "user_agent": request.headers.get("User-Agent", "unknown"),
            },
        )

    @app.after_request
    def after_request(response):
        """
        Выполняется ПОСЛЕ обработки каждого HTTP запроса.

        Действия:
        - Вычисляет время выполнения запроса
        - Логирует результат выполнения (кроме шумных путей)
        - Добавляет Request ID в заголовок ответа
        - Гарантирует корректный Content-Type для JSON
        """
        path = request.path
        request_id = getattr(g, "request_id", "unknown")

        # --- 1. Всегда проставляем X-Request-ID и charset (даже для шумных путей) ---
        response.headers["X-Request-ID"] = request_id

        content_type = response.content_type or ""
        if response.mimetype == "application/json" and "charset=" not in content_type:
            response.headers[
                "Content-Type"] = "application/json; charset=utf-8"

        # --- 2. Шумные пути, которые НЕ логируем детально ---
        noisy_paths = {"/favicon.ico"}
        if path in noisy_paths:
            # Для них мы уже добавили Request ID и charset — просто возвращаем ответ
            return response

        # --- 3. Вычисляем время выполнения запроса (в миллисекундах) ---
        if hasattr(g, "start_time"):
            duration_ms = (time.perf_counter() - g.start_time) * 1000
        else:
            duration_ms = 0

        # --- 4. Определяем уровень логирования по статус-коду ---
        if response.status_code >= 500:
            log_level = logging.ERROR  # 5xx — ошибки сервера
        elif response.status_code >= 400:
            log_level = logging.WARNING  # 4xx — ошибки клиента
        else:
            log_level = logging.INFO  # 2xx, 3xx — успешные запросы

        # --- 5. Формируем payload для логов ---
        extra = {
            "event": "http_request_completed",
            "service": "wine-assistant-api",
            "request_id": request_id,
            "http_method": request.method,
            "http_path": request.path,
            "http_route": getattr(getattr(request, "url_rule", None), "rule",
                                  None),
            "client_ip": request.headers.get("X-Real-IP", request.remote_addr),
            "user_agent": request.user_agent.string if request.user_agent else None,
            "query_string": request.query_string.decode("utf-8",
                                                        errors="ignore"),
            "status_code": response.status_code,
            "duration_ms": round(duration_ms, 2),
            "response_size_bytes": response.content_length or 0,
        }

        # --- 6. Опционально добавляем sku_code, если он есть в контексте запроса ---
        sku_code = getattr(g, "sku_code", None)
        if sku_code is not None:
            extra["sku_code"] = sku_code

        # --- 7. Пишем лог ---
        app.logger.log(
            log_level,
            "HTTP request completed",
            extra=extra,
        )

        return response
