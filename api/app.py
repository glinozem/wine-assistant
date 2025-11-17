#!/usr/bin/env python3
# api/app.py — hardened v0.4.0

import json
import os
import time
from datetime import date, datetime, timezone
from functools import wraps
from typing import Any, Dict, List, Optional, Tuple

from flasgger import Swagger
from flask import Flask, g, jsonify, request
from flask_cors import CORS
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

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
app = Flask(__name__)

APP_VERSION = os.getenv("APP_VERSION", "0.4.0")
STARTED_AT = datetime.now(timezone.utc)
API_KEY = os.getenv("API_KEY")  # if set → protect certain endpoints

# CORS
cors_origins = os.getenv("CORS_ORIGINS", "*")
expose_headers_default = "X-RateLimit-Limit,X-RateLimit-Remaining,X-RateLimit-Reset,X-Request-ID"
expose_headers = os.getenv("CORS_EXPOSE_HEADERS", expose_headers_default)

if cors_origins == "*":
    CORS(app, expose_headers=[h.strip() for h in expose_headers.split(",")])
else:
    origins_list = [o.strip() for o in cors_origins.split(",")]
    CORS(app, origins=origins_list, expose_headers=[h.strip() for h in expose_headers.split(",")])

# Structured JSON logging
from api.logging_config import setup_logging  # noqa: E402

setup_logging(app)

# Flask-Limiter
from flask_limiter import Limiter  # noqa: E402
from flask_limiter.errors import RateLimitExceeded  # noqa: E402
from flask_limiter.util import get_remote_address  # noqa: E402

# Make sure headers are emitted
app.config.update(
    RATELIMIT_HEADERS_ENABLED=True,
    RATELIMIT_HEADER_LIMIT="X-RateLimit-Limit",
    RATELIMIT_HEADER_REMAINING="X-RateLimit-Remaining",
    RATELIMIT_HEADER_RESET="X-RateLimit-Reset",
)

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=[],  # we set limits per-endpoint
    storage_uri=os.getenv("RATE_LIMIT_STORAGE_URL", "memory://"),
    enabled=os.getenv("RATE_LIMIT_ENABLED", "1") == "1",
    headers_enabled=True,
)

PUBLIC_LIMIT = os.getenv("RATE_LIMIT_PUBLIC", "100/hour")
PROTECTED_LIMIT = os.getenv("RATE_LIMIT_PROTECTED", "1000/hour")

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
@app.before_request
def before_request():
    g._started = time.perf_counter()
    g._request_id = f"req_{int(time.time()*1000)%0xFFFFFF:06x}"
    app.logger.info(
        "Incoming request",
        extra={
            "request_id": g._request_id,
            "method": request.method,
            "path": request.path,
            "query_string": request.query_string.decode("utf-8", errors="ignore"),
            "client_ip": request.headers.get("X-Forwarded-For", request.remote_addr),
            "user_agent": request.headers.get("User-Agent"),
        },
    )

@app.after_request
def after_request(resp):
    dur_ms = round((time.perf_counter() - getattr(g, "_started", time.perf_counter())) * 1000, 2)
    app.logger.info(
        "Request completed",
        extra={
            "request_id": getattr(g, "_request_id", "unknown"),
            "method": request.method,
            "path": request.path,
            "status_code": resp.status_code,
            "duration_ms": dur_ms,
            "response_size_bytes": resp.calculate_content_length() or 0,
        },
    )
    # Trace headers
    if hasattr(g, "_request_id"):
        resp.headers["X-Request-ID"] = g._request_id

    # ❗️Ключевая правка: гарантируем Content-Type с charset для JSON
    if resp.mimetype == "application/json" and "charset=" not in resp.content_type:
        resp.headers["Content-Type"] = "application/json; charset=utf-8"

    return resp

@app.errorhandler(RateLimitExceeded)
def handle_ratelimit(e):
    return jsonify({
        "error": "rate_limited",
        "message": "Too many requests. Please retry later."
    }), 429

@app.errorhandler(Exception)
def log_exception(exc):
    app.logger.error(
        "Unhandled exception",
        extra={
            "request_id": getattr(g, "_request_id", "unknown"),
            "path": request.path,
            "exception": repr(exc),
        },
        exc_info=True,
    )
    return jsonify({"error": "internal_error", "request_id": getattr(g, "_request_id", None)}), 500

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
                        "request_id": getattr(g, "_request_id", "unknown"),
                        "path": request.path,
                        "provided_key_prefix": (provided[:8] + "...") if provided else None,
                    },
                )
                return jsonify({"error": "forbidden"}), 403
        return fn(*args, **kwargs)
    return wrapper

# ────────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────────
def _serialize_validation_error(e: ValidationError) -> dict:
    """Превращает pydantic v2 ValidationError в JSON-безопасный словарь."""
    # Берём только безопасные поля без ctx (там могут быть несериализуемые объекты)
    details = [
        {
            "loc": err.get("loc"),
            "msg": err.get("msg"),
            "type": err.get("type"),
        }
        for err in e.errors(include_url=False)
    ]
    return {"error": "validation_error", "details": details}

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


class SimpleSearchParams(BaseModel):
    q: str | None = Field(default=None, max_length=200)
    max_price: float | None = Field(default=None, ge=0)
    color: str | None = Field(default=None, max_length=50)
    region: str | None = Field(default=None, max_length=100)
    limit: int = Field(default=10, ge=1, le=100)

    @field_validator("q")
    @classmethod
    def q_min_len(cls, v: str | None):
        if v is None:
            return v
        v2 = v.strip()
        if v2 and len(v2) < 2:
            raise ValueError("q must be at least 2 characters")
        return v2 or None


class CatalogSearchParams(BaseModel):
    q: str | None = Field(default=None, max_length=200)
    in_stock: bool = False
    limit: int = Field(default=10, ge=1, le=100)

    @field_validator("q")
    @classmethod
    def q_min_len(cls, v: str | None):
        if v is None:
            return v
        v2 = v.strip()
        if v2 and len(v2) < 2:
            raise ValueError("q must be at least 2 characters")
        return v2 or None


# -------- Price / Inventory history params --------
class PriceHistoryParams(BaseModel):
    dt_from: Optional[date] = Field(None, alias="from")
    dt_to: Optional[date] = Field(None, alias="to")
    limit: int = Field(50, ge=1, le=1000)
    offset: int = Field(0, ge=0, le=100_000)

    @model_validator(mode="after")
    def _check_range(self):
        if self.dt_from and self.dt_to and self.dt_from > self.dt_to:
            raise ValueError("'from' must be <= 'to'")
        return self

class InventoryHistoryParams(BaseModel):
    dt_from: Optional[date] = Field(None, alias="from")
    dt_to: Optional[date] = Field(None, alias="to")
    limit: int = Field(50, ge=1, le=1000)
    offset: int = Field(0, ge=0, le=100_000)

    @model_validator(mode="after")
    def _check_range(self):
        if self.dt_from and self.dt_to and self.dt_from > self.dt_to:
            raise ValueError("'from' must be <= 'to'")
        return self
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
        app.logger.error("Readiness check failed - DB unavailable", extra={"error": err})
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
        app.logger.error("Readiness check failed", extra={"error": str(e)}, exc_info=True)
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
        try:
            conn.close()
        except Exception:
            pass

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
    try:
        params = SimpleSearchParams.model_validate(request.args.to_dict(flat=True))
    except ValidationError as e:
        return jsonify(_serialize_validation_error(e)), 400

    conn, err = db_connect()
    if err or not conn:
        app.logger.error("Search failed - database unavailable", extra={"error": err})
        return jsonify({"items": [], "total": 0, "query": params.q})

    try:
        clauses: list[str] = []
        qparams: list = []

        if params.q:
            clauses.append("(p.title_ru ILIKE %s OR p.producer ILIKE %s OR p.region ILIKE %s)")
            like = f"%{params.q}%"
            qparams.extend([like, like, like])

        if params.max_price is not None:
            clauses.append("p.price_final_rub <= %s")
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
                   p.price_list_rub, p.price_final_rub
            FROM public.products p
            {where}
            ORDER BY p.title_ru
            LIMIT %s
        """
        qparams.append(params.limit)
        rows = db_query(conn, sql, tuple(qparams))
        return jsonify({"items": rows, "total": len(rows), "query": params.q})
    except Exception as e:
        app.logger.error(
            "Search query failed",
            extra={"error": str(e), "query": params.q, "limit": params.limit},
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
        try:
            conn.close()
        except Exception:
            pass


@app.route("/catalog/search", methods=["GET"])
@limiter.limit(PUBLIC_LIMIT)
def catalog_search():
    """
    Extended catalog search with pagination and stock info
    ---
    tags: [Search]
    summary: Extended search with pagination
    parameters:
      - in: query
        name: q
        type: string
      - in: query
        name: in_stock
        type: boolean
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
    try:
        params = CatalogSearchParams.model_validate(request.args.to_dict(flat=True))
    except ValidationError as e:
        return jsonify(_serialize_validation_error(e)), 400

    conn, err = db_connect()
    if err or not conn:
        app.logger.error("Catalog search failed - database unavailable", extra={"error": err})
        return jsonify({"items": [], "total": 0, "offset": 0, "limit": params.limit, "query": params.q})

    try:
        clauses: list[str] = []
        qparams: list = []

        if params.q:
            clauses.append("(p.title_ru ILIKE %s OR p.producer ILIKE %s OR p.region ILIKE %s)")
            like = f"%{params.q}%"
            qparams.extend([like, like, like])

        if params.in_stock:
            clauses.append("i.stock_free > 0")

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        sql = f"""
            SELECT p.code, p.title_ru as name, p.producer, p.region, p.color, p.style,
                   p.price_list_rub, p.price_final_rub,
                   i.stock_total, i.stock_free
            FROM public.products p
            LEFT JOIN public.inventory i ON i.code = p.code
            {where}
            ORDER BY COALESCE(i.stock_free, 0) DESC, p.title_ru
            LIMIT %s
        """
        qparams.append(params.limit)

        rows = db_query(conn, sql, tuple(qparams))
        return jsonify({
            "items": rows,
            "total": len(rows),
            "offset": 0,
            "limit": params.limit,
            "query": params.q
        })
    except Exception as e:
        app.logger.error(
            "Catalog search failed",
            extra={"error": str(e), "query": params.q, "limit": params.limit, "in_stock": params.in_stock},
            exc_info=True,
        )
        return jsonify({
            "error": "search_failed",
            "message": "Failed to execute catalog search",
            "items": [],
            "total": 0,
            "offset": 0,
            "limit": params.limit,
            "query": params.q
        }), 500
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ────────────────────────────────────────────────────────────────────────────────
# SKU endpoints (protected if API_KEY set)
# ────────────────────────────────────────────────────────────────────────────────
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
    """
    conn, err = db_connect()
    if err or not conn:
        app.logger.error("SKU lookup failed - DB unavailable", extra={"error": err, "code": code})
        return jsonify({"error": "not_found"}), 404

    try:
        rows = db_query(
            conn,
            """
            SELECT p.code, p.title_ru AS name, p.producer, p.region, p.color, p.style,
                   p.price_list_rub, p.price_final_rub,
                   COALESCE(i.stock_total, 0) AS stock_total,
                   COALESCE(i.stock_free, 0)  AS stock_free
            FROM public.products p
            LEFT JOIN public.inventory i ON i.code = p.code
            WHERE p.code = %s
            """,
            (code,),
        )
        if not rows:
            app.logger.info("SKU not found", extra={"code": code})
            return jsonify({"error": "not_found"}), 404
        return jsonify(rows[0])
    except Exception as e:
        app.logger.error("SKU lookup failed", extra={"error": str(e), "code": code}, exc_info=True)
        return jsonify({"error": "internal_error"}), 500
    finally:
        try:
            conn.close()
        except Exception:
            pass

@app.route("/sku/<code>/price-history", methods=["GET"])
@app.route("/api/v1/sku/<code>/price-history", methods=["GET"])
@require_api_key
@limiter.limit(PROTECTED_LIMIT)
def price_history(code: str):
    """
    Get price history for SKU
    ---
    tags: [Products]
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
    """
    try:
        params = PriceHistoryParams.model_validate(
            request.args.to_dict(flat=True))
    except ValidationError as e:
        return jsonify(_serialize_validation_error(e)), 400

    conn, err = db_connect()
    if err or not conn:
        app.logger.error(
            f"Price history failed - database unavailable: {code}",
            extra={"error": err})
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
        return jsonify({
            "items": rows,
            "total": len(rows),
            "code": code,
            "limit": params.limit,
            "offset": params.offset
        })
    except Exception as e:
        app.logger.error(
            f"Price history lookup failed: {code}",
            extra={"error": str(e), "from": params.dt_from,
                   "to": params.dt_to},
            exc_info=True,
        )
        return jsonify({
            "error": "query_failed",
            "items": [], "total": 0, "code": code,
            "limit": params.limit, "offset": params.offset
        }), 500
    finally:
        try:
            conn.close()
        except Exception:
            pass

@app.route("/sku/<code>/inventory-history", methods=["GET"])
@app.route("/api/v1/sku/<code>/inventory-history", methods=["GET"])
@require_api_key
@limiter.limit(PROTECTED_LIMIT)
def inventory_history(code: str):
    """
    Get inventory history for SKU
    ---
    tags: [Products]
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
    """
    try:
        params = InventoryHistoryParams.model_validate(
            request.args.to_dict(flat=True))
    except ValidationError as e:
        return jsonify(_serialize_validation_error(e)), 400

    conn, err = db_connect()
    if err or not conn:
        app.logger.error(
            f"Inventory history failed - database unavailable: {code}",
            extra={"error": err})
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
            SELECT code, stock_total, reserved, stock_free, as_of
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
            extra={"error": str(e), "from": params.dt_from,
                   "to": params.dt_to},
            exc_info=True,
        )
        return jsonify({
            "error": "query_failed",
            "items": [], "total": 0, "code": code,
            "limit": params.limit, "offset": params.offset
        }), 500
    finally:
        try:
            conn.close()
        except Exception:
            pass

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
