#!/usr/bin/env python3
# api/app.py — hardened v0.4.0

import io
import os
import re
import time
from datetime import date, datetime, timezone
from decimal import Decimal
from functools import wraps
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

from flasgger import Swagger
from flask import Flask, abort, g, jsonify, redirect, render_template, request, send_file, url_for
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.errors import RateLimitExceeded
from flask_limiter.util import get_remote_address
from werkzeug.exceptions import HTTPException

from api.export import ExportService
from api.logging_config import setup_logging
from api.ops_daily_import import register_ops_daily_import
from api.request_middleware import setup_request_logging
from api.schemas import (
    CatalogSearchParams,
    CatalogSort,
    InventoryHistoryParams,
    PriceHistoryParams,
    SimpleSearchParams,
    SkuResponse,
)
from api.validation import validate_query_params

PRICE_EFFECTIVE_SQL = "COALESCE(p.price_final_rub, p.price_list_rub)"


# ────────────────────────────────────────────────────────────────────────────────
# DB setup (psycopg3 → psycopg2 fallback)
# ────────────────────────────────────────────────────────────────────────────────
try:
    import psycopg  # psycopg3
    HAVE_PSYCOPG3 = True
except Exception:  # pragma: no cover
    HAVE_PSYCOPG3 = False
    try:
        import psycopg2  # type: ignore
    except Exception:  # pragma: no cover
        psycopg2 = None  # type: ignore

def db_connect() -> Tuple[Optional[Any], Optional[str]]:
    """
    Open a DB connection using standard PostgreSQL env vars (PG*).
    Returns (conn, error_or_none)
    """
    dsn = {
        "host": os.getenv("PGHOST", "db"),
        "port": int(os.getenv("PGPORT", "5432")),
        "dbname": os.getenv("PGDATABASE", "wine_db"),
        "user": os.getenv("PGUSER", "postgres"),
        "password": os.getenv("PGPASSWORD", "postgres"),
    }
    try:
        if HAVE_PSYCOPG3:
            conn = psycopg.connect(
                host=dsn["host"],
                port=dsn["port"],
                dbname=dsn["dbname"],
                user=dsn["user"],
                password=dsn["password"],
                connect_timeout=3,
            )
            return conn, None
        else:
            if psycopg2 is None:
                return None, "No psycopg available"
            conn = psycopg2.connect(
                host=dsn["host"],
                port=dsn["port"],
                dbname=dsn["dbname"],
                user=dsn["user"],
                password=dsn["password"],
                connect_timeout=3,
            )
            return conn, None
    except Exception as e:
        return None, str(e)

def db_query(conn: Any, sql: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
    """Execute SELECT and return rows as list of dicts (works for psycopg2/3)."""
    params = params or tuple()
    rows: List[Dict[str, Any]] = []
    if HAVE_PSYCOPG3:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            cols = [d.name for d in cur.description]
            for r in cur.fetchall():
                rows.append({c: v for c, v in zip(cols, r)})
    else:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            cols = [d[0] for d in cur.description]
            for r in cur.fetchall():
                rows.append({c: v for c, v in zip(cols, r)})
    return rows

# ────────────────────────────────────────────────────────────────────────────────
# App / CORS / Logging / Rate limiting
# ────────────────────────────────────────────────────────────────────────────────
app = Flask(
    __name__,
    static_folder="../static",   # /app/api -> /app/static
    static_url_path="/static",  # URL вида /static/...
)

APP_VERSION = os.getenv("APP_VERSION", "0.4.0")
STARTED_AT = datetime.now(timezone.utc)
API_KEY = os.getenv("API_KEY")  # if set → protect certain endpoints

# ────────────────────────────────────────────────────────────────────────────────
# Image resolver (local static/images) -> stable URL
# ────────────────────────────────────────────────────────────────────────────────

_IMAGE_EXT_PRIORITY = (".jpeg", ".jpg", ".png", ".webp")
_IMAGE_INDEX: dict[str, str] | None = None


def _get_image_dir() -> Path:
    env_dir = os.getenv("WINE_IMAGE_DIR")
    if env_dir:
        return Path(env_dir)
    # app.static_folder у нас = ../static, значит картинки = ../static/images
    return Path(app.static_folder) / "images"


def _build_image_index() -> dict[str, str]:
    image_dir = _get_image_dir()
    idx: dict[str, str] = {}
    if not image_dir.exists():
        return idx

    priority = {ext: i for i, ext in enumerate(_IMAGE_EXT_PRIORITY)}

    for p in image_dir.iterdir():
        if not p.is_file():
            continue

        stem = p.stem
        if not re.fullmatch(r"D\d+", stem):
            continue

        ext = p.suffix.lower()
        if ext not in priority:
            continue

        prev = idx.get(stem)
        if prev is None:
            idx[stem] = p.name
            continue

        prev_ext = Path(prev).suffix.lower()
        if priority[ext] < priority.get(prev_ext, 999):
            idx[stem] = p.name

    return idx


def _get_best_image_filename(code: str) -> str | None:
    global _IMAGE_INDEX
    if _IMAGE_INDEX is None:
        _IMAGE_INDEX = _build_image_index()
    return _IMAGE_INDEX.get(code)


def _public_url(path: str) -> str:
    base = os.getenv("API_BASE_URL") or os.getenv("PUBLIC_BASE_URL")
    if not base:
        return path  # относительный URL, безопасно
    return urljoin(base.rstrip("/") + "/", path.lstrip("/"))


def _resolve_image_url(code: str, existing_url: Any = None) -> str | None:
    """
    Возвращает стабильный URL на /sku/<code>/image если локальный файл существует.
    Если локального файла нет, но existing_url внешний (http/https) — оставляем его.
    Иначе возвращаем None.
    """
    filename = _get_best_image_filename(code)
    if filename:
        return _public_url(url_for("sku_image", code=code))

    if isinstance(existing_url, str) and existing_url.startswith(("http://", "https://")):
        return existing_url

    return None


@app.route("/ui")
def ui_index():
    # позже сюда можно добавить передачу API-ключа из конфига
    return render_template("ui.html", api_key=API_KEY or "")

@app.route("/daily-import")
def daily_import_ui():
    return render_template("daily_import.html", api_key=API_KEY or "")

# CORS
cors_origins = os.getenv("CORS_ORIGINS", "*")
expose_headers_default = "X-RateLimit-Limit,X-RateLimit-Remaining,X-RateLimit-Reset,X-Request-ID"
expose_headers = os.getenv("CORS_EXPOSE_HEADERS", expose_headers_default)

if cors_origins == "*":
    CORS(app, expose_headers=[h.strip() for h in expose_headers.split(",")])
else:
    origins_list = [o.strip() for o in cors_origins.split(",")]
    CORS(app, origins=origins_list, expose_headers=[h.strip() for h in expose_headers.split(",")])

setup_logging(app)
setup_request_logging(app)

app.config.update(
    RATELIMIT_HEADERS_ENABLED=True,
    RATELIMIT_HEADER_LIMIT="X-RateLimit-Limit",
    RATELIMIT_HEADER_REMAINING="X-RateLimit-Remaining",
    RATELIMIT_HEADER_RESET="X-RateLimit-Reset",
)

RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "1") == "1"

if RATE_LIMIT_ENABLED:
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=[],  # лимиты задаём на эндпоинтах
        storage_uri=os.getenv("RATE_LIMIT_STORAGE_URL", "memory://"),
        headers_enabled=True,
    )
else:
    class _DummyLimiter:
        """Простая заглушка для limiter, когда RATE_LIMIT_ENABLED=0."""

        def limit(self, *args, **kwargs):
            def decorator(fn):
                return fn
            return decorator

    limiter = _DummyLimiter()

PUBLIC_LIMIT = os.getenv("RATE_LIMIT_PUBLIC", "100/hour")
PROTECTED_LIMIT = os.getenv("RATE_LIMIT_PROTECTED", "1000/hour")

export_service = ExportService()

# ────────────────────────────────────────────────────────────────────────────────
# Swagger
# ────────────────────────────────────────────────────────────────────────────────
swagger_template = {
    "swagger": "2.0",
    "info": {
        "title": "Wine Assistant API",
        "version": APP_VERSION,
        "description": "API для поиска цен, ассортимента и витрин (Swagger UI на /docs)",
        "contact": {
            "name": "Wine Assistant Team",
            "url": "https://github.com/glinozem/wine-assistant",
        },
    },
    "securityDefinitions": {
        "ApiKeyAuth": {"type": "apiKey", "name": "X-API-Key", "in": "header"},
    },
    "security": [],
    "definitions": {
        "ProductSearchItem": {
            "type": "object",
            "required": ["code", "name"],
            "properties": {
                "code": {"type": "string", "example": "D010210"},
                "name": {
                    "type": "string",
                    "example": "Delampa Monastrell Делампа Монастрель",
                },
                "producer": {"type": "string"},
                "country": {"type": "string"},
                "region": {"type": "string"},
                "color": {"type": "string"},
                "style": {"type": "string"},
                "grapes": {"type": "string"},
                "vintage": {"type": "integer", "format": "int32"},
                "price_list_rub": {"type": "number", "format": "float"},
                "price_final_rub": {"type": "number", "format": "float"},
                "stock_total": {"type": "integer", "format": "int32"},
                "stock_free": {"type": "integer", "format": "int32"},
                "vivino_rating": {"type": "number", "format": "float"},
                "vivino_url": {"type": "string"},
                "supplier": {"type": "string"},
                "producer_site": {
                    "type": "string",
                    "example": "https://producer.example.com",
                },
                "image_url": {
                    "type": "string",
                    "example": "https://cdn.example.com/wines/D010210.png",
                },
                "winery_name_ru": {
                    "type": "string",
                    "example": "Каза Сантуш Лима",
                },
                "winery_description_ru": {
                    "type": "string",
                    "example": "Семейная винодельня в регионе Лиссабон...",
                },
            },
        },
        "CatalogSearchResponse": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {"$ref": "#/definitions/ProductSearchItem"},
                },
                "total": {"type": "integer", "format": "int32"},
                "offset": {"type": "integer", "format": "int32"},
                "limit": {"type": "integer", "format": "int32"},
                "query": {"type": "string"},
            },
        },
        "SkuResponse": {
            "type": "object",
            "required": ["code", "title_ru", "name"],
            "properties": {
                "code": {"type": "string", "example": "D010210"},
                "title_ru": {
                    "type": "string",
                    "example": "Delampa Monastrell Делампа Монастрель",
                },
                "name": {
                    "type": "string",
                    "example": "Delampa Monastrell Делампа Монастрель",
                },
                "producer": {"type": "string", "example": "Bodegas Delampa"},
                "country": {"type": "string", "example": "Испания"},
                "region": {"type": "string", "example": "Хумилия"},
                "color": {"type": "string", "example": "красное"},
                "style": {"type": "string", "example": "сухое"},
                "grapes": {
                    "type": "string",
                    "example": "Monastrell",
                },
                "vintage": {"type": "integer", "format": "int32", "example": 2020},
                "price_list_rub": {"type": "number", "format": "float"},
                "price_final_rub": {"type": "number", "format": "float"},
                "stock_total": {"type": "integer", "format": "int32"},
                "stock_free": {"type": "integer", "format": "int32"},
                "vivino_rating": {"type": "number", "format": "float"},
                "vivino_url": {"type": "string"},
                "supplier": {"type": "string", "example": "Bodegas Delampa, S.L."},
                "producer_site": {"type": "string"},
                "image_url": {"type": "string"},
                "supplier_ru": {"type": "string", "example": "Бодегас Делампа"},
                "winery_name_ru": {
                    "type": "string",
                    "example": "Каза Сантуш Лима",
                },
                "winery_description_ru": {"type": "string"},
            },
        },
        "PriceHistoryItem": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "example": "D009704"},
                "price_rub": {
                    "type": "number",
                    "format": "float",
                    "example": 1890.0,
                },
                "effective_from": {
                    "type": "string",
                    "format": "date-time",
                    "example": "2025-10-01T00:00:00+03:00",
                },
                "effective_to": {
                    "type": "string",
                    "format": "date-time",
                    "example": "2025-10-22T00:00:00+03:00",
                },
            },
        },
        "PriceHistoryResponse": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "example": "D009704",
                },
                "items": {
                    "type": "array",
                    "items": {"$ref": "#/definitions/PriceHistoryItem"},
                },
                "total": {"type": "integer", "format": "int32", "example": 12},
                "limit": {"type": "integer", "format": "int32", "example": 50},
                "offset": {"type": "integer", "format": "int32", "example": 0},
            },
        },
        "InventoryHistoryItem": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "example": "D009704"},
                "stock_total": {
                    "type": "integer",
                    "format": "int32",
                    "example": 120,
                },
                "reserved": {
                    "type": "integer",
                    "format": "int32",
                    "example": 5,
                },
                "stock_free": {
                    "type": "integer",
                    "format": "int32",
                    "example": 115,
                },
                "as_of": {
                    "type": "string",
                    "format": "date-time",
                    "example": "2025-10-27T12:00:00+03:00",
                },
            },
        },
        "InventoryHistoryResponse": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "example": "D009704",
                },
                "items": {
                    "type": "array",
                    "items": {"$ref": "#/definitions/InventoryHistoryItem"},
                },
                "total": {"type": "integer", "format": "int32", "example": 20},
                "limit": {"type": "integer", "format": "int32", "example": 50},
                "offset": {"type": "integer", "format": "int32", "example": 0},
            },
        },
    },
}

swagger_config = {
    "headers": [],
    "openapi": "2.0",
    "specs": [{"endpoint": "apispec_1", "route": "/apispec_1.json"}],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/docs",
}
Swagger(app, template=swagger_template, config=swagger_config)

# ────────────────────────────────────────────────────────────────────────────────
# Request/Response logging and error handling
# ────────────────────────────────────────────────────────────────────────────────
@app.errorhandler(RateLimitExceeded)
def handle_ratelimit(e):
    return jsonify({
        "error": "rate_limited",
        "message": "Too many requests. Please retry later."
    }), 429

@app.errorhandler(HTTPException)
def handle_http_exception(e: HTTPException):
    """
    Не превращаем HTTP-ошибки (404/400/405/...) в 500.
    Для /api/* возвращаем JSON, для остальных путей — стандартный ответ Flask (404 страница/текст).
    """
    if request.path.startswith("/api/"):
        return jsonify(
            {
                "error": e.name.lower().replace(" ", "_"),
                "message": e.description,
                "request_id": getattr(g, "request_id", None),
            }
        ), e.code

    return e

@app.errorhandler(Exception)
def log_exception(exc):
    app.logger.error(
        "Unhandled exception",
        extra={
            "event": "unhandled_exception",
            "service": "wine-assistant-api",
            "request_id": getattr(g, "request_id", "unknown"),
            "http_method": request.method,
            "http_path": request.path,
            "sku_code": getattr(g, "sku_code", None),
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
        },
        exc_info=True,
    )
    return jsonify(
        {
            "error": "internal_error",
            "request_id": getattr(g, "request_id", None)
        }
    ), 500

# ────────────────────────────────────────────────────────────────────────────────
# Security
# ────────────────────────────────────────────────────────────────────────────────
def require_api_key(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if API_KEY:
            provided = request.headers.get("X-API-Key")
            if provided != API_KEY:
                app.logger.warning(
                    "Invalid API key attempt",
                    extra={
                        "event": "invalid_api_key",
                        "service": "wine-assistant-api",
                        "request_id": getattr(g, "request_id", "unknown"),
                        "http_method": request.method,
                        "http_path": request.path,
                        "client_ip": request.remote_addr,
                        "provided_key_prefix": (provided[
                                                    :8] + "...") if provided else None,
                    },
                )
                return jsonify({"error": "forbidden"}), 403
        return fn(*args, **kwargs)
    return wrapper


# ────────────────────────────────────────────────────────────────────────────────
# Ops: Daily Import endpoints
# ────────────────────────────────────────────────────────────────────────────────
register_ops_daily_import(app, require_api_key, db_connect, db_query)


# ────────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────────
def _parse_int(name: str, default: int) -> int:
    try:
        v = int(request.args.get(name, default))
        return v
    except Exception:
        return default

def _parse_bool(name: str, default: bool = False) -> bool:
    raw = request.args.get(name)
    if raw is None:
        return default
    return str(raw).lower() in ("1", "true", "yes", "on")

def _parse_date(name: str) -> Optional[date]:
    raw = request.args.get(name)
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except Exception:
            pass
    return None

def _convert_decimal_to_number(value):
    """Привести Decimal/строки с числом к int/float, остальные значения вернуть как есть."""
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)

    if isinstance(value, str):
        s = value.strip().replace(" ", "").replace("\xa0", "")
        if not s:
            return value
        # сначала пробуем int
        try:
            return int(s)
        except ValueError:
            # потом float (учтём возможную запятую)
            try:
                return float(s.replace(",", "."))
            except ValueError:
                return value

    return value


def _normalize_product_row(row: dict) -> dict:
    """
    Привести числовые поля товара к нормальным числам,
    чтобы в JSON они были number, а не string.
    """
    for key in (
        "price_list_rub",
        "price_final_rub",
        "stock_total",
        "stock_free",
        "vivino_rating",
    ):
        if key in row:
            row[key] = _convert_decimal_to_number(row[key])
    code = row.get("code")
    if isinstance(code, str) and code:
        row["image_url"] = _resolve_image_url(code, row.get("image_url"))
    return row


def _normalize_price_and_inventory_row(row: dict) -> dict:
    """
    Универсальный нормализатор числовых полей для строк с ценами/остатками.
    Подойдёт для простого поиска и любых выборок, где есть price_* и stock_*.
    """
    # сначала используем уже существующую логику для цен/остатков/рейтинга
    row = _normalize_product_row(row)

    # при необходимости — расширяем дополнительными полями остатков
    for key in ("reserved",):
        if key in row:
            row[key] = _convert_decimal_to_number(row[key])

    return row


def _close_conn_safely(conn: Any | None) -> None:
    """
    Аккуратно закрывает DB-соединение, игнорируя любые ошибки при закрытии.

    Безопасно вызывать даже с conn=None.
    """
    if not conn:
        return
    try:
        conn.close()
    except Exception:
        # Ничего не логируем: мы и так в finally, и не хотим
        # маскировать исходную ошибку более поздней.
        pass


# ────────────────────────────────────────────────────────────────────────────────
# Health endpoints
# ────────────────────────────────────────────────────────────────────────────────
@app.route("/health", methods=["GET"])
@limiter.limit(PUBLIC_LIMIT)
def health():
    """
    Basic health check
    ---
    tags: [Health]
    responses:
      200:
        description: OK
    """
    return jsonify({"ok": True})

@app.route("/live", methods=["GET"])
@limiter.limit(PUBLIC_LIMIT)
def liveness():
    """
    Liveness probe
    ---
    tags: [Health]
    responses:
      200: {description: Alive}
    """
    now = datetime.now(timezone.utc)
    return jsonify(
        {
            "status": "alive",
            "started_at": STARTED_AT.isoformat(),
            "timestamp": now.isoformat(),
            "uptime_seconds": (now - STARTED_AT).total_seconds(),
            "version": APP_VERSION,
        }
    )

@app.route("/ready", methods=["GET"])
@limiter.limit(PUBLIC_LIMIT)
def readiness():
    """
    Readiness probe — checks DB availability and basic objects.
    ---
    tags: [Health]
    responses:
      200: {description: Ready}
      503: {description: Not Ready}
    """
    now = datetime.now(timezone.utc)
    start_time = time.perf_counter()

    conn, err = db_connect()
    if err or not conn:
        app.logger.error(
            "Readiness check failed - DB unavailable",
            extra={
                "event": "readiness_db_unavailable",
                "service": "wine-assistant-api",
                "request_id": getattr(g, "request_id", "unknown"),
                "http_method": request.method,
                "http_path": request.path,
                "error_message": err,
            },
        )
        return (
            jsonify(
                {
                    "status": "not_ready",
                    "timestamp": now.isoformat(),
                    "version": APP_VERSION,
                    "checks": {"database": {"status": "down", "error": err}},
                }
            ),
            503,
        )

    checks = {}
    try:
        version_rows = db_query(conn, "SELECT version()")
        pg_version = version_rows[0]["version"] if version_rows else "unknown"

        required_tables = ["products", "product_prices", "inventory", "inventory_history"]
        existing_tables = db_query(
            conn,
            """
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public' AND tablename = ANY(%s)
            """,
            (required_tables,),
        )
        found_tables = [row["tablename"] for row in existing_tables]

        required_indexes = [
            "idx_inventory_code_free",
            "idx_inventory_history_code_time",
            "ux_product_prices_code_from",
        ]
        existing_indexes = db_query(
            conn,
            """
            SELECT indexname FROM pg_indexes
            WHERE schemaname = 'public' AND indexname = ANY(%s)
            """,
            (required_indexes,),
        )
        found_indexes = [row["indexname"] for row in existing_indexes]

        required_constraints = ["chk_product_prices_nonneg"]
        existing_constraints = db_query(
            conn,
            "SELECT conname FROM pg_constraint WHERE conname = ANY(%s)",
            (required_constraints,),
        )
        found_constraints = [row["conname"] for row in existing_constraints]

        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

        checks["database"] = {
            "status": "up",
            "latency_ms": latency_ms,
            "version": pg_version,
            "tables": found_tables,
            "indexes": found_indexes,
            "constraints": found_constraints,
        }

        response_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return jsonify(
            {
                "status": "ready",
                "timestamp": now.isoformat(),
                "version": APP_VERSION,
                "checks": checks,
                "response_time_ms": response_time_ms,
            }
        )
    except Exception as e:
        app.logger.error(
            "Readiness check failed",
            extra={
                "event": "readiness_check_failed",
                "service": "wine-assistant-api",
                "request_id": getattr(g, "request_id", "unknown"),
                "http_method": request.method,
                "http_path": request.path,
                "error_type": type(e).__name__,
                "error_message": str(e),
            },
            exc_info=True,
        )
        return (
            jsonify(
                {
                    "status": "not_ready",
                    "timestamp": now.isoformat(),
                    "version": APP_VERSION,
                    "checks": {"database": {"status": "error", "error": str(e)}},
                }
            ),
            503,
        )
    finally:
        _close_conn_safely(conn)

@app.route("/version", methods=["GET"])
@limiter.limit(PUBLIC_LIMIT)
def version():
    """
    Get API version & build metadata
    ---
    tags:
      - Meta
    summary: Get API version and build metadata
    description: Returns application version and build metadata such as version, commit SHA and build timestamp.
    produces:
      - application/json
    responses:
      200:
        description: Version info
        schema:
          type: object
          properties:
            version:
              type: string
              example: "0.4.0"
            build_date:
              type: string
              format: date-time
              example: "2025-11-11T12:57:36Z"
            commit_sha:
              type: string
              example: "a1b2c3d"
            python_version:
              type: string
              example: "3.11.9"
            app_name:
              type: string
              example: "wine-assistant"
      429:
        description: Too many requests — rate limit exceeded
        schema:
          type: object
          properties:
            error:
              type: string
              example: rate_limited
            message:
              type: string
              example: Too many requests. Please retry later.
    """

    return jsonify({"version": APP_VERSION})

# ────────────────────────────────────────────────────────────────────────────────
# Search endpoints
# ────────────────────────────────────────────────────────────────────────────────
@app.route("/search", methods=["GET"])
@limiter.limit(PUBLIC_LIMIT)
def simple_search():
    """
    Simple search in catalog
    ---
    tags: [Search]
    summary: Simple search by query string
    parameters:
      - in: query
        name: q
        type: string
      - in: query
        name: max_price
        type: number
      - in: query
        name: color
        type: string
      - in: query
        name: region
        type: string
      - in: query
        name: limit
        type: integer
        default: 10
    responses:
      200:
        description: Search results
      400:
        description: Validation error
    """
    params, error = validate_query_params(SimpleSearchParams)
    if error:
        return error

    conn, err = db_connect()
    if err or not conn:
        app.logger.error(
            "Search failed - database unavailable",
            extra={
                "event": "simple_search_db_unavailable",
                "service": "wine-assistant-api",
                "request_id": getattr(g, "request_id", "unknown"),
                "http_method": request.method,
                "http_path": request.path,
                "error_message": err,
                "query": params.q,
                "limit": params.limit,
            },
        )
        return jsonify({"items": [], "total": 0, "query": params.q})

    try:
        clauses: list[str] = []
        qparams: list = []

        if params.q:
            clauses.append("(p.title_ru ILIKE %s OR p.producer ILIKE %s OR p.region ILIKE %s)")
            like = f"%{params.q}%"
            qparams.extend([like, like, like])

        if params.max_price is not None:
            clauses.append(f"{PRICE_EFFECTIVE_SQL} <= %s")
            qparams.append(params.max_price)

        if params.color:
            clauses.append("p.color ILIKE %s")
            qparams.append(f"%{params.color}%")

        if params.region:
            clauses.append("p.region ILIKE %s")
            qparams.append(f"%{params.region}%")

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        sql = f"""
            SELECT p.code, p.title_ru as name, p.producer, p.region, p.color,
                   p.price_list_rub, COALESCE(p.price_final_rub, p.price_list_rub) AS price_final_rub
            FROM public.products p
            {where}
            ORDER BY p.title_ru
            LIMIT %s
        """
        qparams.append(params.limit)
        rows = db_query(conn, sql, tuple(qparams))
        items = [_normalize_price_and_inventory_row(dict(r)) for r in rows]

        return jsonify(
            {"items": items, "total": len(items), "query": params.q})
    except Exception as e:
        app.logger.error(
            "Search query failed",
            extra={
                "event": "simple_search_failed",
                "service": "wine-assistant-api",
                "request_id": getattr(g, "request_id", "unknown"),
                "http_method": request.method,
                "http_path": request.path,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "query": params.q,
                "limit": params.limit,
            },
            exc_info=True,
        )
        return jsonify({
            "error": "search_failed",
            "message": "Failed to execute search",
            "items": [],
            "total": 0,
            "query": params.q
        }), 500
    finally:
        _close_conn_safely(conn)


@app.route("/catalog/search", methods=["GET"])
@app.route("/api/v1/products/search", methods=["GET"])
@limiter.limit(PUBLIC_LIMIT)
def catalog_search():
    """
    Extended catalog search with pagination and stock/price filters.

    Версионированный эндпоинт `/api/v1/products/search` и его алиас
    `/catalog/search`. Используется для поиска товаров в каталоге.
    ---
    tags: [Search]
    summary: Catalog search with filters and pagination
    parameters:
      - in: query
        name: q
        type: string
        required: false
        description: Поиск по названию, производителю и региону
      - in: query
        name: country
        type: string
      - in: query
        name: region
        type: string
      - in: query
        name: grapes
        type: string
      - in: query
        name: in_stock
        type: boolean
        default: false
        description: Только позиции с положительным свободным остатком
      - in: query
        name: min_price
        type: number
      - in: query
        name: max_price
        type: number
      - in: query
        name: sort
        type: string
        enum: [price_asc, price_desc, name_asc, name_desc, code_asc, code_desc]
      - in: query
        name: offset
        type: integer
        default: 0
      - in: query
        name: limit
        type: integer
        default: 10
    responses:
      200:
        description: Catalog search results
        schema:
          $ref: '#/definitions/CatalogSearchResponse'
      400:
        description: Validation error
    """
    params, error = validate_query_params(CatalogSearchParams)
    if error:
        return error

    is_api = request.path.startswith("/api/")
    effective_offset = params.offset if is_api else 0

    conn, err = db_connect()
    if err or not conn:
        app.logger.error(
            "Catalog search failed - database unavailable",
            extra={
                "event": "catalog_search_db_unavailable",
                "service": "wine-assistant-api",
                "request_id": getattr(g, "request_id", "unknown"),
                "http_method": request.method,
                "http_path": request.path,
                "error_message": err,
                "query": params.q,
                "limit": params.limit,
                "offset": effective_offset,
                "in_stock": params.in_stock,
            },
        )
        # Возвращаем "пустую" выдачу, но с корректными метаданными
        return jsonify(
            {
                "items": [],
                "total": 0,
                "offset": effective_offset,
                "limit": params.limit,
                "query": params.q,
            }
        )

    try:
        clauses: list[str] = []
        qparams: list = []

        # Текстовый поиск
        if params.q:
            clauses.append(
                "(p.title_ru ILIKE %s OR p.producer ILIKE %s OR COALESCE(p.region, w.region) ILIKE %s)"
            )
            like = f"%{params.q}%"
            qparams.extend([like, like, like])

        # Фильтры по справочникам
        if params.country:
            clauses.append("p.country ILIKE %s")
            qparams.append(f"%{params.country}%")

        if params.region:
            clauses.append("COALESCE(p.region, w.region) ILIKE %s")
            qparams.append(f"%{params.region}%")

        if params.grapes:
            clauses.append("p.grapes ILIKE %s")
            qparams.append(f"%{params.grapes}%")

        # Остатки
        if params.in_stock:
            clauses.append("i.stock_free > 0")

        # Диапазон цен
        if params.min_price is not None:
            clauses.append(f"{PRICE_EFFECTIVE_SQL} >= %s")
            qparams.append(params.min_price)

        if params.max_price is not None:
            clauses.append(f"{PRICE_EFFECTIVE_SQL} <= %s")
            qparams.append(params.max_price)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        # Сортировка
        order_by = "COALESCE(i.stock_free, 0) DESC, p.title_ru"

        if params.sort == CatalogSort.PRICE_ASC:
            order_by = f"{PRICE_EFFECTIVE_SQL} ASC NULLS LAST, p.title_ru ASC, p.code ASC"
        elif params.sort == CatalogSort.PRICE_DESC:
            order_by = f"{PRICE_EFFECTIVE_SQL} DESC NULLS LAST, p.title_ru ASC, p.code ASC"
        elif params.sort == CatalogSort.NAME_ASC:
            order_by = "p.title_ru ASC"
        elif params.sort == CatalogSort.NAME_DESC:
            order_by = "p.title_ru DESC"
        elif params.sort == CatalogSort.CODE_ASC:
            order_by = "p.code ASC"
        elif params.sort == CatalogSort.CODE_DESC:
            order_by = "p.code DESC"

        # LIMIT обязателен для обоих эндпоинтов,
        # а OFFSET – только для /api/v1/products/search.
        limit_clause = "LIMIT %s"
        qparams.append(params.limit)

        # Для нового API поддерживаем OFFSET в SQL,
        # а для legacy /catalog/search сохраняем старое поведение
        # (без OFFSET), чтобы не ломать тесты и клиентов.
        if is_api:
            limit_clause += "\n            OFFSET %s"
            qparams.append(effective_offset)

        sql = f"""
            SELECT
                p.code,
                p.title_ru        AS name,
                p.producer,
                p.country,
                COALESCE(p.region, w.region)         AS region,
                p.color,
                p.style,
                p.grapes,
                p.vintage,
                p.vivino_url,
                p.vivino_rating,
                p.supplier,
                COALESCE(p.producer_site, w.producer_site) AS producer_site,
                p.image_url,
                p.price_list_rub AS price_list_rub,
                COALESCE(p.price_final_rub, p.price_list_rub) AS price_final_rub,
                i.stock_total,
                i.stock_free,
                w.supplier_ru     AS winery_name_ru,
                w.description_ru  AS winery_description_ru
            FROM public.products p
            LEFT JOIN public.inventory i ON i.code = p.code
            LEFT JOIN public.wineries  w ON w.supplier = p.supplier
            {where}
            ORDER BY {order_by}
            {limit_clause}
        """

        rows = db_query(conn, sql, tuple(qparams))

        items = [_normalize_price_and_inventory_row(dict(row)) for row in rows]

        return jsonify(
            {
                "items": items,
                "total": len(items),
                "offset": effective_offset,
                "limit": params.limit,
                "query": params.q,
            }
        )

    except Exception as e:
        app.logger.error(
            "Catalog search failed",
            extra={
                "event": "catalog_search_failed",
                "service": "wine-assistant-api",
                "request_id": getattr(g, "request_id", "unknown"),
                "http_method": request.method,
                "http_path": request.path,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "query": params.q,
                "limit": params.limit,
                "offset": effective_offset,
                "in_stock": params.in_stock,
            },
            exc_info=True,
        )
        return (
            jsonify(
                {
                    "error": "search_failed",
                    "message": "Failed to execute catalog search",
                    "items": [],
                    "total": 0,
                    "offset": effective_offset,
                    "limit": params.limit,
                    "query": params.q,
                }
            ),
            500,
        )
    finally:
        _close_conn_safely(conn)


@app.route("/export/search", methods=["GET"])
@app.route("/api/v1/export/search", methods=["GET"])
@limiter.limit(PUBLIC_LIMIT)
def export_search():
    """
    Export catalog search results.

    ---
    tags: [Export]
    summary: Export catalog search results
    description: >
      Экспорт результатов `/api/v1/products/search` в Excel/PDF/JSON.
      Поддерживает те же фильтры, что и основной search.
    parameters:
      - in: query
        name: q
        type: string
        description: Текстовый поиск по названию/производителю/региону
      - in: query
        name: max_price
        type: number
      - in: query
        name: min_price
        type: number
      - in: query
        name: color
        type: string
      - in: query
        name: region
        type: string
      - in: query
        name: country
        type: string
      - in: query
        name: in_stock
        type: boolean
      - in: query
        name: limit
        type: integer
        default: 100
        description: Максимальное количество строк для экспорта
      - in: query
        name: format
        type: string
        enum: [xlsx, pdf, json]
        default: xlsx
        description: Формат экспорта
      - in: query
        name: fields
        type: string
        description: >
          Список полей через запятую (например: code,title_ru,price_final_rub,region).
          Если не задан, используется дефолтный набор.
    responses:
      200:
        description: Exported file
      400:
        description: Validation error or unsupported format
    """
    # 1. Разбираем format/fields
    fmt = request.args.get("format", "xlsx").lower()
    if fmt not in ("xlsx", "pdf", "json"):
        return (
            jsonify(
                {
                    "error": "unsupported_format",
                    "supported": ["xlsx", "pdf", "json"],
                }
            ),
            400,
        )

    raw_fields = request.args.get("fields")
    fields: list[str] | None = None
    if raw_fields:
        fields = [f.strip() for f in raw_fields.split(",") if f.strip()]

    # 2. Переиспользуем ту же валидацию, что и для /api/v1/products/search
    #    но limit для экспорта можно сделать больше дефолта (например, 100 или 1000)
    params, error = validate_query_params(CatalogSearchParams)
    if error:
        return error

    # Для экспорта разумно ограничить лимит сверху, чтобы не убить прод
    export_limit = min(params.limit, 1000)
    params.limit = export_limit

    conn, err = db_connect()
    if err or not conn:
        app.logger.error(
            "Export search failed - database unavailable",
            extra={
                "event": "export_search_db_unavailable",
                "service": "wine-assistant-api",
                "request_id": getattr(g, "request_id", "unknown"),
                "http_method": request.method,
                "http_path": request.path,
                "error_message": err,
                "query": params.q,
                "limit": params.limit,
            },
        )
        # Для экспорта в случае проблем можно вернуть JSON-ошибку
        return jsonify({"error": "db_unavailable"}), 503

    try:
        # Здесь мы по сути копируем query-часть catalog_search,
        # но вместо json ответа возвращаем данные в Excel/PDF/JSON через ExportService.
        clauses: list[str] = []
        qparams: list = []

        if params.q:
            clauses.append(
                "(p.title_ru ILIKE %s OR p.producer ILIKE %s OR p.region ILIKE %s)"
            )
            like = f"%{params.q}%"
            qparams.extend([like, like, like])

        if params.country:
            clauses.append("p.country ILIKE %s")
            qparams.append(f"%{params.country}%")

        if params.region:
            clauses.append("p.region ILIKE %s")
            qparams.append(f"%{params.region}%")

        if params.grapes:
            clauses.append("p.grapes ILIKE %s")
            qparams.append(f"%{params.grapes}%")

        if params.in_stock:
            clauses.append("i.stock_free > 0")

        if params.min_price is not None:
            clauses.append(f"{PRICE_EFFECTIVE_SQL} >= %s")
            qparams.append(params.min_price)

        if params.max_price is not None:
            clauses.append(f"{PRICE_EFFECTIVE_SQL} <= %s")
            qparams.append(params.max_price)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        # Для экспорта сортировка по названию — наиболее ожидаемое поведение
        order_by = "p.title_ru"

        sql = f"""
            SELECT
                p.code,
                p.title_ru,
                p.producer,
                p.country,
                p.region,
                p.color,
                p.style,
                p.grapes,
                p.vintage,
                p.vivino_url,
                p.vivino_rating,
                p.supplier,
                p.producer_site,
                p.image_url,
                p.price_list_rub AS price_list_rub,
                COALESCE(p.price_final_rub, p.price_list_rub) as price_final_rub,
                COALESCE(i.stock_total, 0) AS stock_total,
                COALESCE(i.stock_free, 0)  AS stock_free
            FROM public.products p
            LEFT JOIN public.inventory i ON i.code = p.code
            {where}
            ORDER BY {order_by}
            LIMIT %s
        """

        qparams.append(params.limit)

        rows = db_query(conn, sql, tuple(qparams))

        # 3. В зависимости от формата используем ExportService
        if fmt == "json":
            items = [_normalize_product_row(dict(row)) for row in rows]
            return jsonify({
                "value": items,
                "Count": len(items),
            })

        if fmt == "xlsx":
            content = export_service.export_search_to_excel(rows, fields)
            return send_file(
                io.BytesIO(content),
                mimetype=(
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                ),
                as_attachment=True,
                download_name="wine_search.xlsx",
            )

        if fmt == "pdf":
            content = export_service.export_search_to_pdf(rows)
            return send_file(
                io.BytesIO(content),
                mimetype="application/pdf",
                as_attachment=True,
                download_name="wine_search.pdf",
            )

        # сюда по идее не дойдём
        return jsonify({"error": "unsupported_format"}), 400

    except Exception as e:
        app.logger.error(
            "Export search failed",
            extra={
                "event": "export_search_failed",
                "service": "wine-assistant-api",
                "request_id": getattr(g, "request_id", "unknown"),
                "http_method": request.method,
                "http_path": request.path,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "query": params.q,
                "limit": params.limit,
            },
            exc_info=True,
        )
        return jsonify({"error": "export_failed"}), 500
    finally:
        _close_conn_safely(conn)


# ────────────────────────────────────────────────────────────────────────────────
# SKU endpoints (protected if API_KEY set)
# ────────────────────────────────────────────────────────────────────────────────

def _fetch_sku_row(conn, code: str) -> dict | None:
    """
    Общая выборка SKU из products + inventory + wineries.
    Используется и для /api/v1/sku, и для /api/v1/export/sku.
    """
    rows = db_query(
        conn,
        """
        SELECT
            p.code,
            p.title_ru                 AS title_ru,
            p.title_ru                 AS name,
            p.producer,
            p.country,
            p.region,
            p.color,
            p.style,
            p.grapes,
            p.vintage,
            p.vivino_url,
            p.vivino_rating,
            p.supplier,
            p.producer_site,
            p.image_url,
            p.price_list_rub AS price_list_rub,
            COALESCE(p.price_final_rub, p.price_list_rub) as price_final_rub,
            COALESCE(i.stock_total, 0) AS stock_total,
            COALESCE(i.stock_free, 0)  AS stock_free,
            -- данные из справочника виноделен
            w.supplier_ru              AS supplier_ru,
            w.supplier_ru              AS winery_name_ru,
            w.description_ru           AS winery_description_ru
        FROM public.products p
        LEFT JOIN public.inventory i
               ON i.code = p.code
        LEFT JOIN public.wineries w
               ON w.supplier = p.supplier
        WHERE p.code = %s
        """,
        (code,),
    )

    if not rows:
        app.logger.info(
            "SKU not found in _fetch_sku_row",
            extra={
                "event": "sku_not_found",
                "service": "wine-assistant-api",
                "request_id": getattr(g, "request_id", "unknown"),
                "http_method": request.method,
                "http_path": request.path,
                "sku_code": code,
            },
        )
        return None

    row = dict(rows[0])
    row = _normalize_product_row(row)

    # гарантируем наличие ключей, чтобы ExportService и API не спотыкались
    row.setdefault("producer_site", None)
    row.setdefault("image_url", None)
    row.setdefault("supplier_ru", None)
    row.setdefault("winery_name_ru", None)
    row.setdefault("winery_description_ru", None)

    return row


@app.route("/sku/<code>/image", methods=["GET"])
def sku_image(code: str):
    # Не даём использовать endpoint как “файловый прокси” для произвольных имён
    if not re.fullmatch(r"D\d+", code or ""):
        abort(404)

    filename = _get_best_image_filename(code)
    if not filename:
        abort(404)

    return redirect(url_for("static", filename=f"images/{filename}"), code=302)


@app.route("/sku/<code>", methods=["GET"])
@app.route("/api/v1/sku/<code>", methods=["GET"])
@require_api_key
@limiter.limit(PROTECTED_LIMIT)
def get_sku(code: str):
    """
    Get product card by SKU code
    ---
    tags: [Products]
    security: [ { ApiKeyAuth: [] } ]
    parameters:
      - in: path
        name: code
        required: true
        type: string
    responses:
      200:
        description: SKU card
        schema:
          $ref: '#/definitions/SkuResponse'
      404:
        description: SKU not found
    """
    g.sku_code = code
    conn, err = db_connect()
    if err or not conn:
        app.logger.error(
            "SKU lookup failed - DB unavailable",
            extra={
                "event": "sku_lookup_db_unavailable",
                "service": "wine-assistant-api",
                "request_id": getattr(g, "request_id", "unknown"),
                "http_method": request.method,
                "http_path": request.path,
                "error_message": err,
                "sku_code": code,
            },
        )
        return jsonify({"error": "not_found"}), 404

    try:
        row = _fetch_sku_row(conn, code)
        if row is None:
            return jsonify({"error": "not_found"}), 404

        payload = SkuResponse(**row).model_dump()
        return jsonify(payload)
    except Exception as e:  # noqa: BLE001
        app.logger.error(
            "SKU lookup failed",
            extra={
                "event": "sku_lookup_failed",
                "service": "wine-assistant-api",
                "request_id": getattr(g, "request_id", "unknown"),
                "http_method": request.method,
                "http_path": request.path,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "sku_code": code,
            },
            exc_info=True,
        )
        return jsonify({"error": "internal_error"}), 500
    finally:
        _close_conn_safely(conn)

@app.route("/export/sku/<code>", methods=["GET"])
@app.route("/api/v1/export/sku/<code>", methods=["GET"])
@require_api_key
@limiter.limit(PROTECTED_LIMIT)
def export_sku(code: str):
    """
    Export SKU card
    ---
    tags: [Export]
    security: [ { ApiKeyAuth: [] } ]
    parameters:
      - in: path
        name: code
        required: true
        type: string
      - in: query
        name: format
        type: string
        enum: [pdf, json]
        default: pdf
        description: Формат экспорта (pdf или json)
    responses:
      200:
        description: Exported SKU card
      400:
        description: Unsupported format
      404:
        description: SKU not found
    """
    g.sku_code = code
    app.logger.info(
        "export_sku called",
        extra={
            "event": "export_sku_called",
            "service": "wine-assistant-api",
            "request_id": getattr(g, "request_id", "unknown"),
            "http_method": request.method,
            "http_path": request.path,
            "sku_code": code,
        },
    )

    format_type = request.args.get("format", "pdf").lower()
    if format_type not in ("pdf", "json"):
        return (
            jsonify(
                {
                    "error": "unsupported_format",
                    "supported": ["pdf", "json"],
                }
            ),
            400,
        )

    conn, err = db_connect()
    if err or not conn:
        app.logger.error(
            "Export SKU failed - DB unavailable",
            extra={
                "event": "export_sku_db_unavailable",
                "service": "wine-assistant-api",
                "request_id": getattr(g, "request_id", "unknown"),
                "http_method": request.method,
                "http_path": request.path,
                "sku_code": code,
                "error": err,
            },
        )
        return jsonify({"error": "internal_error"}), 503

    try:
        wine = _fetch_sku_row(conn, code)
        if wine is None:
            return jsonify({"error": "not_found"}), 404

        # format=json → отдаём те же данные, что и /api/v1/sku
        if format_type == "json":
            return jsonify(wine)

        # format=pdf → отдаём в ExportService
        pdf_data = export_service.export_wine_card_to_pdf(wine)

        return send_file(
            io.BytesIO(pdf_data),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"wine_card_{code}.pdf",
        )

    except Exception as e:  # noqa: BLE001
        app.logger.error(
            "Export SKU failed",
            extra={
                "event": "export_sku_failed",
                "service": "wine-assistant-api",
                "request_id": getattr(g, "request_id", "unknown"),
                "http_method": request.method,
                "http_path": request.path,
                "sku_code": code,
                "error": str(e),
            },
            exc_info=True,
        )
        return jsonify({"error": "export_failed"}), 500
    finally:
        _close_conn_safely(conn)


@app.route("/sku/<code>/price-history", methods=["GET"])
@app.route("/api/v1/sku/<code>/price-history", methods=["GET"])
@require_api_key
@limiter.limit(PROTECTED_LIMIT)
def price_history(code: str):
    """
    Get price history for SKU

    ---
    tags: [Products]
    summary: Price history for SKU
    description: >
      Возвращает историю цен для одного SKU из таблицы product_prices.
      Поддерживает фильтрацию по диапазону дат и пагинацию.
    security: [ { ApiKeyAuth: [] } ]
    parameters:
      - in: path
        name: code
        required: true
        type: string
        description: Код SKU (например, D009704)
      - in: query
        name: from
        type: string
        format: date
        required: false
        description: Начало диапазона (YYYY-MM-DD, по effective_from::date)
      - in: query
        name: to
        type: string
        format: date
        required: false
        description: Конец диапазона (YYYY-MM-DD, включительно)
      - in: query
        name: limit
        type: integer
        default: 50
        description: Максимальное количество записей в ответе
      - in: query
        name: offset
        type: integer
        default: 0
        description: Смещение для пагинации
    responses:
      200:
        description: Price history data
        schema:
          $ref: '#/definitions/PriceHistoryResponse'
      400:
        description: Validation error (невалидный диапазон дат или параметры)
      500:
        description: Internal error during price history lookup
    """
    g.sku_code = code
    params, error = validate_query_params(PriceHistoryParams)
    if error:
        return error

    conn, err = db_connect()
    if err or not conn:
        app.logger.error(
            f"Price history failed - database unavailable: {code}",
            extra={
                "event": "price_history_db_unavailable",
                "service": "wine-assistant-api",
                "request_id": getattr(g, "request_id", "unknown"),
                "http_method": request.method,
                "http_path": request.path,
                "sku_code": code,
                "dt_from": params.dt_from,
                "dt_to": params.dt_to,
                "error": err,
            },
        )
        return jsonify({"items": [], "total": 0, "code": code})

    try:
        clauses = ["code = %s"]
        sql_params: list = [code]

        if params.dt_from:
            clauses.append("effective_from::date >= %s")
            sql_params.append(params.dt_from)
        if params.dt_to:
            clauses.append("effective_from::date <= %s")
            sql_params.append(params.dt_to)

        where = " AND ".join(clauses)
        sql = f"""
            SELECT code, price_rub, effective_from, effective_to
            FROM public.product_prices
            WHERE {where}
            ORDER BY effective_from DESC
            LIMIT %s OFFSET %s
        """
        sql_params.extend([params.limit, params.offset])

        rows = db_query(conn, sql, tuple(sql_params))

        # Нормализуем цену, чтобы в JSON был number, а не строка
        for r in rows:
            if "price_rub" in r:
                r["price_rub"] = _convert_decimal_to_number(r["price_rub"])

        return jsonify({
            "code": code,
            "items": rows,
            "total": len(rows),
            "limit": params.limit,
            "offset": params.offset,
        })
    except Exception as e:
        app.logger.error(
            f"Price history lookup failed: {code}",
            extra={
                "event": "price_history_lookup_failed",
                "service": "wine-assistant-api",
                "request_id": getattr(g, "request_id", "unknown"),
                "http_method": request.method,
                "http_path": request.path,
                "sku_code": code,
                "dt_from": params.dt_from,
                "dt_to": params.dt_to,
                "error": str(e),
            },
            exc_info=True,
        )
        return jsonify({
            "error": "query_failed",
            "items": [], "total": 0, "code": code,
            "limit": params.limit, "offset": params.offset
        }), 500
    finally:
        _close_conn_safely(conn)


@app.route("/export/price-history/<code>", methods=["GET"])
@app.route("/api/v1/export/price-history/<code>", methods=["GET"])
@require_api_key
@limiter.limit(PROTECTED_LIMIT)
def export_price_history(code: str):
    """
    Export price history for SKU
    ---
    tags: [Export]
    security: [ { ApiKeyAuth: [] } ]
    parameters:
      - in: path
        name: code
        required: true
        type: string
      - in: query
        name: from
        type: string
        format: date
      - in: query
        name: to
        type: string
        format: date
      - in: query
        name: limit
        type: integer
        default: 50
      - in: query
        name: offset
        type: integer
        default: 0
      - in: query
        name: format
        type: string
        enum: [xlsx, json]
        default: xlsx
        description: Формат экспорта (Excel или JSON)
    responses:
      200:
        description: Exported price history
      400:
        description: Unsupported format or validation error
    """
    g.sku_code = code  # чтобы sku_code попадал в middleware-логи

    fmt = request.args.get("format", "xlsx").lower()
    if fmt not in ("xlsx", "json"):
        return (
            jsonify(
                {
                    "error": "unsupported_format",
                    "supported": ["xlsx", "json"],
                }
            ),
            400,
        )

    params, error = validate_query_params(PriceHistoryParams)
    if error:
        return error

    conn, err = db_connect()
    if err or not conn:
        app.logger.error(
            "Export price history failed - database unavailable",
            extra={
                "event": "export_price_history_db_unavailable",
                "service": "wine-assistant-api",
                "request_id": getattr(
                    g, "request_id", getattr(g, "_request_id", "unknown")
                ),
                "http_method": request.method,
                "http_path": request.path,
                "sku_code": code,
                "dt_from": params.dt_from,
                "dt_to": params.dt_to,
                "error": err,
            },
        )
        return jsonify({"error": "db_unavailable"}), 503

    try:
        clauses = ["code = %s"]
        sql_params: list = [code]

        if params.dt_from:
            clauses.append("effective_from::date >= %s")
            sql_params.append(params.dt_from)
        if params.dt_to:
            clauses.append("effective_from::date <= %s")
            sql_params.append(params.dt_to)

        where = " AND ".join(clauses)
        sql = f"""
            SELECT code, price_rub, effective_from, effective_to
            FROM public.product_prices
            WHERE {where}
            ORDER BY effective_from DESC
            LIMIT %s OFFSET %s
        """
        sql_params.extend([params.limit, params.offset])

        rows = db_query(conn, sql, tuple(sql_params))

        # Приводим к формату, который ожидает ExportService.export_price_history_to_excel
        items: list[dict] = []
        for r in rows:
            items.append(
                {
                    "effective_from": str(r["effective_from"]),
                    "effective_to": str(r["effective_to"]) if r["effective_to"] else None,
                    # В БД одна цена, дублируем в прайс/финальную
                    "price_list_rub": r["price_rub"],
                    "price_final_rub": r["price_rub"],
                }
            )

        history = {
            "code": code,
            "items": items,
            "total": len(items),
            "limit": params.limit,
            "offset": params.offset,
        }

        # ✅ метрика успешного экспорта для Grafana
        app.logger.info(
            "Export price history succeeded",
            extra={
                "event": "export_price_history_succeeded",
                "service": "wine-assistant-api",
                "request_id": getattr(
                    g, "request_id", getattr(g, "_request_id", "unknown")
                ),
                "http_method": request.method,
                "http_path": request.path,
                "sku_code": code,
                "dt_from": params.dt_from,
                "dt_to": params.dt_to,
                "items_returned": history["total"],
                "format": fmt,
            },
        )

        if fmt == "json":
            # Нормализуем числа в JSON
            for item in history["items"]:
                item["price_list_rub"] = _convert_decimal_to_number(
                    item["price_list_rub"]
                )
                item["price_final_rub"] = _convert_decimal_to_number(
                    item["price_final_rub"]
                )
            return jsonify(history)

        # Excel-экспорт через ExportService
        xlsx_bytes = export_service.export_price_history_to_excel(history)

        return send_file(
            io.BytesIO(xlsx_bytes),
            mimetype=(
                "application/vnd.openxmlformats-"
                "officedocument.spreadsheetml.sheet"
            ),
            as_attachment=True,
            download_name=f"price_history_{code}.xlsx",
        )
    except Exception as e:  # noqa: BLE001
        app.logger.error(
            "Export price history failed",
            extra={
                "event": "export_price_history_failed",
                "service": "wine-assistant-api",
                "request_id": getattr(
                    g, "request_id", getattr(g, "_request_id", "unknown")
                ),
                "http_method": request.method,
                "http_path": request.path,
                "sku_code": code,
                "dt_from": params.dt_from,
                "dt_to": params.dt_to,
                "error": str(e),
            },
            exc_info=True,
        )
        return jsonify({"error": "export_failed"}), 500
    finally:
        _close_conn_safely(conn)


@app.route("/export/inventory-history/<code>", methods=["GET"])
@app.route("/api/v1/export/inventory-history/<code>", methods=["GET"])
@require_api_key
@limiter.limit(PROTECTED_LIMIT)
def export_inventory_history(code: str):
    """
    Export inventory history for SKU
    ---
    tags: [Export]
    security: [ { ApiKeyAuth: [] } ]
    parameters:
      - in: path
        name: code
        required: true
        type: string
        description: Код SKU (например, D009704)
      - in: query
        name: from
        type: string
        format: date
        required: false
        description: Начало диапазона (YYYY-MM-DD, по as_of::date)
      - in: query
        name: to
        type: string
        format: date
        required: false
        description: Конец диапазона (YYYY-MM-DD, включительно)
      - in: query
        name: limit
        type: integer
        default: 50
      - in: query
        name: offset
        type: integer
        default: 0
      - in: query
        name: format
        type: string
        enum: [xlsx, json]
        default: xlsx
        description: Формат экспорта (Excel или JSON)
    responses:
      200:
        description: Exported inventory history
      400:
        description: Unsupported format or validation error
    """
    g.sku_code = code
    fmt = request.args.get("format", "xlsx").lower()
    if fmt not in ("xlsx", "json"):
        return (
            jsonify(
                {
                    "error": "unsupported_format",
                    "supported": ["xlsx", "json"],
                }
            ),
            400,
        )

    # те же параметры, что и у /api/v1/sku/<code>/inventory-history
    params, error = validate_query_params(InventoryHistoryParams)
    if error:
        return error

    conn, err = db_connect()
    if err or not conn:
        app.logger.error(
            "Export inventory history failed - database unavailable",
            extra={
                "event": "export_inventory_history_db_unavailable",
                "service": "wine-assistant-api",
                "request_id": getattr(g, "request_id", "unknown"),
                "http_method": request.method,
                "http_path": request.path,
                "sku_code": code,
                "dt_from": params.dt_from,
                "dt_to": params.dt_to,
                "error": err,
            },
        )
        return jsonify({"error": "db_unavailable"}), 503

    try:
        clauses = ["code = %s"]
        sql_params: list = [code]

        if params.dt_from:
            clauses.append("as_of::date >= %s")
            sql_params.append(params.dt_from)
        if params.dt_to:
            clauses.append("as_of::date <= %s")
            sql_params.append(params.dt_to)

        where = " AND ".join(clauses)
        sql = f"""
            SELECT
                code,
                stock_total::bigint AS stock_total,
                reserved::bigint    AS reserved,
                stock_free::bigint  AS stock_free,
                as_of
            FROM public.inventory_history
            WHERE {where}
            ORDER BY as_of DESC
            LIMIT %s OFFSET %s
        """
        sql_params.extend([params.limit, params.offset])

        rows = db_query(conn, sql, tuple(sql_params))

        # Приводим к формату, который ожидает ExportService.export_inventory_history_to_excel
        items: list[dict] = []
        for r in rows:
            items.append(
                {
                    "as_of": str(r["as_of"]),
                    "stock_total": int(r["stock_total"]) if r["stock_total"] is not None else None,
                    "stock_free": int(r["stock_free"]) if r["stock_free"] is not None else None,
                    "reserved": int(r["reserved"]) if r["reserved"] is not None else None,
                }
            )

        history = {
            "code": code,
            "items": items,
            "total": len(items),
            "limit": params.limit,
            "offset": params.offset,
        }

        if fmt == "json":
            return jsonify(history)

        # fmt == "xlsx"
        content = export_service.export_inventory_history_to_excel(history)

        app.logger.info(
            "Export inventory history succeeded",
            extra={
                "event": "export_inventory_history_succeeded",
                "service": "wine-assistant-api",
                "request_id": getattr(g, "request_id", getattr(g, "_request_id", "unknown")),
                "http_method": request.method,
                "http_path": request.path,
                "sku_code": code,
                "dt_from": params.dt_from,
                "dt_to": params.dt_to,
                "items_returned": len(history["items"]),
                "format": fmt,
            },
        )

        return send_file(
            io.BytesIO(content),
            mimetype=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
            as_attachment=True,
            download_name=f"inventory_history_{code}.xlsx",
        )

    except Exception as e:  # noqa: BLE001
        app.logger.error(
            "Export inventory history failed",
            extra={
                "event": "export_inventory_history_failed",
                "service": "wine-assistant-api",
                "request_id": getattr(
                    g, "request_id", getattr(g, "_request_id", "unknown")
                ),
                "http_method": request.method,
                "http_path": request.path,
                "sku_code": code,
                "dt_from": params.dt_from,
                "dt_to": params.dt_to,
                "error": str(e),
            },
            exc_info=True,
        )
        return jsonify({"error": "export_failed"}), 500
    finally:
        _close_conn_safely(conn)


@app.route("/sku/<code>/inventory-history", methods=["GET"])
@app.route("/api/v1/sku/<code>/inventory-history", methods=["GET"])
@require_api_key
@limiter.limit(PROTECTED_LIMIT)
def inventory_history(code: str):
    """
    Get inventory history for SKU

    ---
    tags: [Products]
    summary: Inventory history for SKU
    description: >
      Возвращает историю остатков по SKU из таблицы inventory_history.
      Можно ограничить по диапазону дат и использовать пагинацию.
    security: [ { ApiKeyAuth: [] } ]
    parameters:
      - in: path
        name: code
        required: true
        type: string
        description: Код SKU (например, D009704)
      - in: query
        name: from
        type: string
        format: date
        required: false
        description: Начало диапазона (YYYY-MM-DD, по as_of::date)
      - in: query
        name: to
        type: string
        format: date
        required: false
        description: Конец диапазона (YYYY-MM-DD, включительно)
      - in: query
        name: limit
        type: integer
        default: 50
        description: Максимальное количество записей в ответе
      - in: query
        name: offset
        type: integer
        default: 0
        description: Смещение для пагинации
    responses:
      200:
        description: Inventory history data
        schema:
          $ref: '#/definitions/InventoryHistoryResponse'
      400:
        description: Validation error (невалидный диапазон дат или параметры)
      500:
        description: Internal error during inventory history lookup
    """
    g.sku_code = code
    params, error = validate_query_params(InventoryHistoryParams)
    if error:
        return error

    conn, err = db_connect()
    if err or not conn:
        app.logger.error(
            f"Inventory history failed - database unavailable: {code}",
            extra={
                "event": "inventory_history_db_unavailable",
                "service": "wine-assistant-api",
                "request_id": getattr(g, "request_id", "unknown"),
                "http_method": request.method,
                "http_path": request.path,
                "sku_code": code,
                "dt_from": params.dt_from,
                "dt_to": params.dt_to,
                "error": err,
            },
        )
        return jsonify({"items": [], "total": 0, "code": code})

    try:
        clauses = ["code = %s"]
        sql_params: list = [code]

        if params.dt_from:
            clauses.append("as_of::date >= %s")
            sql_params.append(params.dt_from)
        if params.dt_to:
            clauses.append("as_of::date <= %s")
            sql_params.append(params.dt_to)

        where = " AND ".join(clauses)
        sql = f"""
            SELECT
                code,
                stock_total::bigint AS stock_total,
                reserved::bigint    AS reserved,
                stock_free::bigint  AS stock_free,
                as_of
            FROM public.inventory_history
            WHERE {where}
            ORDER BY as_of DESC
            LIMIT %s OFFSET %s
        """

        sql_params.extend([params.limit, params.offset])

        rows = db_query(conn, sql, tuple(sql_params))
        return jsonify({
            "items": rows,
            "total": len(rows),
            "code": code,
            "limit": params.limit,
            "offset": params.offset
        })
    except Exception as e:
        app.logger.error(
            f"Inventory history lookup failed: {code}",
            extra={
                "event": "inventory_history_lookup_failed",
                "service": "wine-assistant-api",
                "request_id": getattr(g, "request_id", "unknown"),
                "http_method": request.method,
                "http_path": request.path,
                "sku_code": code,
                "dt_from": params.dt_from,
                "dt_to": params.dt_to,
                "error": str(e),
            },
            exc_info=True,
        )
        return jsonify({
            "error": "query_failed",
            "items": [], "total": 0, "code": code,
            "limit": params.limit, "offset": params.offset
        }), 500
    finally:
        _close_conn_safely(conn)

# ────────────────────────────────────────────────────────────────────────────────
# Entrypoint (dev only; production uses Gunicorn with api.wsgi:app)
# ────────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    host = os.getenv("FLASK_HOST", "127.0.0.1")  # безопасный дефолт
    # Явно разрешить внешний биндинг можно FLASK_HOST=0.0.0.0 (например, в докере)
    if host == "0.0.0.0":
        print("⚠️  Dev server is exposed on 0.0.0.0 — ensure this is intentional.")

    if debug:
        app.logger.warning(
            "Running in DEBUG mode with Flask development server. DO NOT use this in production!"
        )

    app.run(host=host, port=port, debug=debug)
