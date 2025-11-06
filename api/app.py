# api/app.py

import os
import time
from datetime import datetime
from functools import wraps

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from flasgger import Swagger
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Импорты для structured logging
from api.logging_config import setup_logging
from api.request_middleware import setup_request_logging

load_dotenv()

app = Flask(__name__)
app.start_time = time.time()

# Настройка structured logging
setup_logging(app)
setup_request_logging(app)

# CORS configuration
cors_origins = os.getenv("CORS_ORIGINS", "*")
if cors_origins == "*":
    CORS(app)  # Разрешить все источники (только для разработки!)
else:
    origins_list = [origin.strip() for origin in cors_origins.split(",")]
    CORS(app, origins=origins_list)

# Swagger configuration
swagger_config = {
    "headers": [],
    "specs": [
        {
            "endpoint": "apispec_1",
            "route": "/apispec_1.json",
            "rule_filter": lambda rule: True,
            "model_filter": lambda tag: True,
        }
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/docs",
}

swagger_template = {
    "info": {
        "title": "Wine Assistant API",
        "description": "API для поиска вин, управления прайсами и остатками",
        "version": os.getenv("APP_VERSION", "0.3.0"),
        "contact": {
            "name": "Wine Assistant Team",
            "url": "https://github.com/glinozem/wine-assistant",
        },
    },
    "securityDefinitions": {
        "ApiKeyAuth": {
            "type": "apiKey",
            "name": "X-API-Key",
            "in": "header",
            "description": "API ключ для доступа к защищённым эндпоинтам",
        }
    },
    "security": [],
}

swagger = Swagger(app, config=swagger_config, template=swagger_template)

# Rate Limiting configuration
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=[os.getenv("RATE_LIMIT_PUBLIC", "100/hour")],
    storage_uri=os.getenv("RATE_LIMIT_STORAGE_URL", "memory://"),
    enabled=os.getenv("RATE_LIMIT_ENABLED", "1") == "1",
    headers_enabled=True,
    swallow_errors=True,  # Don't crash if Redis unavailable
)


@app.errorhandler(429)
def ratelimit_handler(e):
    """Custom handler for rate limit exceeded errors."""
    return jsonify(
        {
            "error": "rate_limit_exceeded",
            "message": "Too many requests. Please try again later.",
            "retry_after": e.description,
        }
    ), 429


# JSON всегда в UTF-8 без \uXXXX
app.json.ensure_ascii = False  # Flask ≥ 2.2
app.config["JSON_AS_ASCII"] = False  # совместимость


@app.after_request
def force_utf8(resp):
    # Явно укажем кодировку для JSON, чтобы PowerShell/клиенты не путались
    if resp.mimetype == "application/json":
        resp.headers["Content-Type"] = "application/json; charset=utf-8"
    return resp


API_KEY = os.getenv("API_KEY")


def require_api_key(f):
    @wraps(f)
    def wrapped(*a, **kw):
        if API_KEY and (request.headers.get("X-API-Key") != API_KEY):
            return jsonify({"error": "forbidden"}), 403
        return f(*a, **kw)

    return wrapped


def get_db():
    """Получить подключение к БД."""
    return psycopg2.connect(
        host=os.getenv("PGHOST", "127.0.0.1"),
        port=int(os.getenv("PGPORT", "5432")),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", "postgres"),
        dbname=os.getenv("PGDATABASE", "wine_db"),
    )


@app.route("/health", methods=["GET"])
def health():
    """
    Basic health check
    ---
    tags:
      - Health
    summary: Simple health check endpoint
    description: Returns OK if the API is running. Does not check database.
    responses:
      200:
        description: API is running
        schema:
          type: object
          properties:
            ok:
              type: boolean
              example: true
        examples:
          application/json: {"ok": true}
    """
    return jsonify({"ok": True})


@app.route("/live", methods=["GET"])
def liveness():
    """
    Liveness probe
    ---
    tags:
      - Health
    summary: Liveness probe for Kubernetes
    description: |
      Quick health check without database connection.
      Returns API status, version, and uptime.
      Used by Kubernetes/Docker for liveness monitoring.
    responses:
      200:
        description: API is alive
        schema:
          type: object
          properties:
            status:
              type: string
              example: "alive"
            version:
              type: string
              example: "0.3.0"
            uptime_seconds:
              type: number
              example: 3661.5
            timestamp:
              type: string
              format: date-time
              example: "2025-10-21T12:34:56.789123Z"
        examples:
          application/json: {
            "status": "alive",
            "version": "0.3.0",
            "uptime_seconds": 3661.5,
            "timestamp": "2025-10-21T12:34:56.789123Z"
          }
    """
    uptime = time.time() - app.start_time
    return jsonify(
        {
            "status": "alive",
            "version": os.getenv("APP_VERSION", "unknown"),
            "uptime_seconds": uptime,
            "timestamp": datetime.now().isoformat() + "Z",
        }
    )


@app.route("/ready", methods=["GET"])
def readiness():
    """
    Readiness probe
    ---
    tags:
      - Health
    summary: Readiness probe for Kubernetes
    description: |
      Deep health check with database validation.
      Checks database connection, tables, indexes, and constraints.
      Returns HTTP 503 if not ready.
    responses:
      200:
        description: API is ready
        schema:
          type: object
          properties:
            status:
              type: string
              example: "ready"
            version:
              type: string
              example: "0.3.0"
            response_time_ms:
              type: number
              example: 14.68
            timestamp:
              type: string
              format: date-time
            checks:
              type: object
              properties:
                database:
                  type: object
                  properties:
                    ok:
                      type: boolean
                    latency_ms:
                      type: number
                    tables:
                      type: object
                    indexes:
                      type: object
                    constraints:
                      type: object
      503:
        description: API is not ready
        schema:
          type: object
          properties:
            status:
              type: string
              example: "not ready"
            error:
              type: string
    """
    start_time = time.time()

    try:
        conn = get_db()
        cur = conn.cursor()

        # Check tables
        cur.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name IN
                  ('products', 'product_prices', 'inventory',
                   'inventory_history')
        """)
        existing_tables = {row[0] for row in cur.fetchall()}

        # Check indexes
        cur.execute("""
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND indexname IN
                  ('products_code_idx', 'products_search_idx',
                   'product_prices_sku_effective_from_idx')
        """)
        existing_indexes = {row[0] for row in cur.fetchall()}

        # Check constraints
        cur.execute("""
            SELECT constraint_name
            FROM information_schema.table_constraints
            WHERE table_schema = 'public'
              AND constraint_name = 'products_pkey'
        """)
        existing_constraints = {row[0] for row in cur.fetchall()}

        cur.close()

        db_latency = (time.time() - start_time) * 1000

        checks = {
            "database": {
                "ok": True,
                "latency_ms": round(db_latency, 2),
                "tables": {
                    "products": "products" in existing_tables,
                    "product_prices": "product_prices" in existing_tables,
                    "inventory": "inventory" in existing_tables,
                    "inventory_history": "inventory_history" in existing_tables,
                },
                "indexes": {
                    "products_code_idx": "products_code_idx" in existing_indexes,
                    "products_search_idx": "products_search_idx" in existing_indexes,
                    "product_prices_sku_effective_from_idx": "product_prices_sku_effective_from_idx"
                    in existing_indexes,
                },
                "constraints": {"products_pkey": "products_pkey" in existing_constraints},
            }
        }

        response_time = (time.time() - start_time) * 1000

        return jsonify(
            {
                "status": "ready",
                "version": os.getenv("APP_VERSION", "unknown"),
                "response_time_ms": round(response_time, 2),
                "timestamp": datetime.now().isoformat() + "Z",
                "checks": checks,
            }
        ), 200

    except Exception as e:
        return jsonify(
            {
                "status": "not ready",
                "version": os.getenv("APP_VERSION", "unknown"),
                "error": str(e),
                "checks": {"database": {"ok": False, "error": str(e)}},
            }
        ), 503


@app.route("/version", methods=["GET"])
def version():
    """
    Get API version
    ---
    tags:
      - Health
    summary: Get API version information
    description: Returns current API version from environment variable APP_VERSION
    responses:
      200:
        description: Version information
        schema:
          type: object
          properties:
            version:
              type: string
              example: "0.3.0"
        examples:
          application/json: {"version": "0.3.0"}
    """
    return jsonify({"version": os.getenv("APP_VERSION", "0.3.0")})


@app.route("/search", methods=["GET"])
def search():
    """
    Search wines in catalog
    ---
    tags:
      - Search
    summary: Search wines by text query and filters
    description: |
      Public endpoint for wine search.
      Filters by **final price** (price_final_rub - with discount applied).
      Text search uses pg_trgm similarity on search_text and title_en.
      Returns both prices: price_list_rub and price_final_rub.
    parameters:
      - name: q
        in: query
        type: string
        required: false
        description: Search query (wine name, producer, region)
        example: "венето"
      - name: max_price
        in: query
        type: number
        required: false
        description: Maximum final price in RUB
        example: 3000
      - name: color
        in: query
        type: string
        required: false
        description: Wine color filter
        example: "красное"
      - name: region
        in: query
        type: string
        required: false
        description: Region filter
        example: "тоскана"
      - name: style
        in: query
        type: string
        required: false
        description: Wine style filter
        example: "сухое"
      - name: limit
        in: query
        type: integer
        required: false
        default: 10
        description: Maximum number of results
        example: 10
    responses:
      200:
        description: Search results
        schema:
          type: object
          properties:
            items:
              type: array
              items:
                type: object
                properties:
                  code:
                    type: string
                  producer:
                    type: string
                  title_ru:
                    type: string
                  title_en:
                    type: string
                  country:
                    type: string
                  region:
                    type: string
                  color:
                    type: string
                  style:
                    type: string
                  grapes:
                    type: string
                  abv:
                    type: number
                  pack:
                    type: string
                  volume:
                    type: string
                  price_list_rub:
                    type: number
                    description: List price (before discount)
                  price_final_rub:
                    type: number
                    description: Final price (with discount applied)
            query:
              type: string
              description: Search query that was used
        examples:
          application/json: {
            "items": [
              {
                "code": "W12345",
                "producer": "Antinori",
                "title_ru": "Тиньянелло",
                "title_en": "Tignanello",
                "country": "Италия",
                "region": "Тоскана",
                "color": "красное",
                "style": "сухое",
                "grapes": "Санджовезе, Каберне Совиньон",
                "abv": 14.0,
                "pack": "бутылка",
                "volume": "0.75",
                "price_list_rub": 8500.0,
                "price_final_rub": 7650.0
              }
            ],
            "query": "тоскана"
          }
    """
    q = (request.args.get("q") or "").strip()
    max_price = request.args.get("max_price", type=float)
    color = request.args.get("color")
    region = request.args.get("region")
    style = request.args.get("style")
    limit = request.args.get("limit", default=10, type=int)

    where = []
    params = []

    if max_price is not None:
        where.append("p.price_final_rub <= %s")
        params.append(max_price)
    if color:
        where.append("p.color ILIKE %s")
        params.append(f"%{color}%")
    if region:
        where.append("p.region ILIKE %s")
        params.append(f"%{region}%")
    if style:
        where.append("p.style ILIKE %s")
        params.append(f"%{style}%")

    order_sql = "ORDER BY p.price_final_rub ASC, p.code ASC"
    order_params = []
    if q:
        where.append("(p.search_text ILIKE %s OR COALESCE(p.title_en,'') ILIKE %s)")
        params.extend([f"%{q}%", f"%{q}%"])
        order_sql = "ORDER BY similarity(p.search_text, %s) DESC NULLS LAST, p.price_final_rub ASC"
        order_params = [q]

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    sql = f"""
        SELECT
          p.code, p.producer, p.title_ru, p.title_en,
          p.country, p.region, p.color, p.style,
          p.grapes, p.abv, p.pack, p.volume,
          p.price_list_rub, p.price_final_rub
        FROM products p
        {where_sql}
        {order_sql}
        LIMIT %s
    """

    with (
        get_db() as conn,
        conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur,
    ):
        cur.execute("SET pg_trgm.similarity_threshold = 0.1;")
        cur.execute(sql, (*params, *order_params, limit))
        rows = cur.fetchall()

    return jsonify({"items": rows, "query": q})


@app.route("/catalog/search", methods=["GET"])
def catalog_search():
    """
    Advanced catalog search with pagination and inventory
    ---
    tags:
      - Search
    summary: Extended search with pagination, inventory, and stock info
    description: |
      Extended search endpoint with pagination and inventory data.
      Filters by **final price** (price_final_rub).
      Returns computed fields: stock_total, reserved, stock_free, in_stock.
    parameters:
      - name: q
        in: query
        type: string
        required: false
        description: Search query
        example: "бароло"
      - name: max_price
        in: query
        type: number
        required: false
        description: Maximum final price in RUB
        example: 5000
      - name: color
        in: query
        type: string
        required: false
        description: Wine color filter
        example: "белое"
      - name: region
        in: query
        type: string
        required: false
        description: Region filter
        example: "пьемонт"
      - name: style
        in: query
        type: string
        required: false
        description: Wine style filter
        example: "сухое"
      - name: grape
        in: query
        type: string
        required: false
        description: Grape variety filter
        example: "неббиоло"
      - name: in_stock
        in: query
        type: string
        required: false
        enum: ["true", "false"]
        description: Filter by stock availability
        example: "true"
      - name: limit
        in: query
        type: integer
        required: false
        default: 20
        description: Maximum number of results per page
        example: 20
      - name: offset
        in: query
        type: integer
        required: false
        default: 0
        description: Number of results to skip (for pagination)
        example: 0
    responses:
      200:
        description: Search results with pagination
        schema:
          type: object
          properties:
            items:
              type: array
              items:
                type: object
                properties:
                  code:
                    type: string
                  producer:
                    type: string
                  title_ru:
                    type: string
                  country:
                    type: string
                  region:
                    type: string
                  color:
                    type: string
                  price_list_rub:
                    type: number
                  price_final_rub:
                    type: number
                  stock_total:
                    type: integer
                    description: Total inventory
                  reserved:
                    type: integer
                    description: Reserved quantity
                  stock_free:
                    type: integer
                    description: Available quantity (total - reserved)
                  in_stock:
                    type: boolean
                    description: True if stock_free > 0
            total:
              type: integer
              description: Total number of results (for pagination)
            limit:
              type: integer
            offset:
              type: integer
            query:
              type: string
        examples:
          application/json: {
            "items": [
              {
                "code": "W67890",
                "producer": "Gaja",
                "title_ru": "Барбареско",
                "region": "Пьемонт",
                "color": "красное",
                "price_list_rub": 12000.0,
                "price_final_rub": 10800.0,
                "stock_total": 15,
                "reserved": 2,
                "stock_free": 13,
                "in_stock": true
              }
            ],
            "total": 42,
            "limit": 20,
            "offset": 0,
            "query": "пьемонт"
          }
    """
    q = (request.args.get("q") or "").strip()
    max_price = request.args.get("max_price", type=float)
    color = request.args.get("color")
    region = request.args.get("region")
    style = request.args.get("style")
    grape = request.args.get("grape")
    in_stock = request.args.get("in_stock", type=str)  # "true"/"false"/None
    limit = request.args.get("limit", default=20, type=int)
    offset = request.args.get("offset", default=0, type=int)

    where, params = [], []
    if max_price is not None:
        where.append("p.price_final_rub <= %s")
        params.append(max_price)
    if color:
        where.append("p.color ILIKE %s")
        params.append(f"%{color}%")
    if region:
        where.append("p.region ILIKE %s")
        params.append(f"%{region}%")
    if style:
        where.append("p.style ILIKE %s")
        params.append(f"%{style}%")
    if grape:
        where.append("p.grapes ILIKE %s")
        params.append(f"%{grape}%")

    # Наличие
    if in_stock == "true":
        where.append("COALESCE(i.stock_free, i.stock_total, 0) > 0")
    elif in_stock == "false":
        where.append("COALESCE(i.stock_free, i.stock_total, 0) <= 0")

    # Поиск/сортировка
    order_sql = "ORDER BY p.price_final_rub ASC, p.code ASC"
    order_params = []
    if q:
        where.append("(p.search_text ILIKE %s OR COALESCE(p.title_en,'') ILIKE %s)")
        params.extend([f"%{q}%", f"%{q}%"])
        order_sql = "ORDER BY similarity(p.search_text, %s) DESC NULLS LAST, p.price_final_rub ASC"
        order_params = [q]

    where_sql = ("WHERE " + " AND ".join(where)) if where else "WHERE TRUE"

    sql = f"""
      SELECT
        p.code, p.producer, p.title_ru, p.title_en,
        p.country, p.region, p.color, p.style,
        p.grapes, p.abv, p.pack, p.volume,
        p.price_list_rub, p.price_final_rub,
        COALESCE(i.stock_total, 0) AS stock_total,
        COALESCE(i.reserved, 0)    AS reserved,
        COALESCE(i.stock_free, COALESCE(i.stock_total,0) - COALESCE(i.reserved,0)) AS stock_free,
        (COALESCE(i.stock_free, i.stock_total, 0) > 0) AS in_stock,
        COUNT(*) OVER() AS total_count
      FROM products p
      LEFT JOIN inventory i ON i.code = p.code
      {where_sql}
      {order_sql}
      LIMIT %s OFFSET %s
    """

    with (
        get_db() as conn,
        conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur,
    ):
        cur.execute("SET pg_trgm.similarity_threshold = 0.1;")
        cur.execute(sql, (*params, *order_params, limit, offset))
        rows = cur.fetchall()

    total = rows[0]["total_count"] if rows else 0
    for r in rows:
        r.pop("total_count", None)

    return jsonify({"items": rows, "total": total, "limit": limit, "offset": offset, "query": q})


@app.route("/sku/<code>", methods=["GET"])
@limiter.limit(os.getenv("RATE_LIMIT_PROTECTED", "1000/hour"))
@require_api_key
def get_sku(code: str):
    """
    Get product card by SKU code
    ---
    tags:
      - Products
    summary: Get detailed product information
    description: |
      Returns complete product information including both prices and current price from history.
      **Requires API key authentication.**
    security:
      - ApiKeyAuth: []
    parameters:
      - name: code
        in: path
        type: string
        required: true
        description: Product SKU code
        example: "D011283"
    responses:
      200:
        description: Product details
        schema:
          type: object
          properties:
            code:
              type: string
            producer:
              type: string
            title_ru:
              type: string
            title_en:
              type: string
            country:
              type: string
            region:
              type: string
            color:
              type: string
            style:
              type: string
            grapes:
              type: string
            abv:
              type: number
            pack:
              type: string
            volume:
              type: string
            price_list_rub:
              type: number
              description: List price (before discount)
            price_final_rub:
              type: number
              description: Final price (with discount)
            current_price:
              type: number
              description: Current price from price history (if available)
        examples:
          application/json: {
            "code": "D011283",
            "producer": "Fontanafredda",
            "title_ru": "Бароло DOCG",
            "title_en": "Barolo DOCG",
            "country": "Италия",
            "region": "Пьемонт",
            "color": "красное",
            "style": "сухое",
            "grapes": "Неббиоло",
            "abv": 14.0,
            "pack": "бутылка",
            "volume": "0.75",
            "price_list_rub": 4500.0,
            "price_final_rub": 4050.0,
            "current_price": 4050.0
          }
      403:
        description: Forbidden - invalid or missing API key
        schema:
          type: object
          properties:
            error:
              type: string
              example: "forbidden"
      404:
        description: Product not found
        schema:
          type: object
          properties:
            error:
              type: string
              example: "not_found"
    """
    sql = """
        SELECT
          p.*,
          pp.price_rub AS current_price
        FROM products p
        LEFT JOIN LATERAL (
          SELECT price_rub
          FROM product_prices
          WHERE code = p.code AND effective_to IS NULL
          ORDER BY effective_from DESC
          LIMIT 1
        ) pp ON TRUE
        WHERE p.code = %s
    """
    with (
        get_db() as conn,
        conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur,
    ):
        cur.execute(sql, (code,))
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "not_found"}), 404
        return jsonify(row)


@app.route("/sku/<code>/price-history", methods=["GET"])
@limiter.limit(os.getenv("RATE_LIMIT_PROTECTED", "1000/hour"))
@require_api_key
def price_history(code: str):
    """
    Get price history for SKU
    ---
    tags:
      - Products
    summary: Get historical price changes
    description: |
      Returns price history from product_prices table.
      **Requires API key authentication.**
    security:
      - ApiKeyAuth: []
    parameters:
      - name: code
        in: path
        type: string
        required: true
        description: Product SKU code
        example: "D011283"
      - name: from
        in: query
        type: string
        format: date
        required: false
        description: Start date (YYYY-MM-DD)
        example: "2025-01-01"
      - name: to
        in: query
        type: string
        format: date
        required: false
        description: End date (YYYY-MM-DD)
        example: "2025-01-31"
      - name: limit
        in: query
        type: integer
        required: false
        default: 50
        description: Maximum number of records
        example: 50
      - name: offset
        in: query
        type: integer
        required: false
        default: 0
        description: Number of records to skip
        example: 0
    responses:
      200:
        description: Price history records
        schema:
          type: object
          properties:
            code:
              type: string
            items:
              type: array
              items:
                type: object
                properties:
                  price_rub:
                    type: number
                  effective_from:
                    type: string
                    format: date-time
                  effective_to:
                    type: string
                    format: date-time
                    nullable: true
            limit:
              type: integer
            offset:
              type: integer
        examples:
          application/json: {
            "code": "D011283",
            "items": [
              {
                "price_rub": 4050.0,
                "effective_from": "2025-01-20T00:00:00",
                "effective_to": null
              },
              {
                "price_rub": 3800.0,
                "effective_from": "2024-12-01T00:00:00",
                "effective_to": "2025-01-19T23:59:59"
              }
            ],
            "limit": 50,
            "offset": 0
          }
      403:
        description: Forbidden - invalid or missing API key
    """
    limit = request.args.get("limit", default=50, type=int)
    offset = request.args.get("offset", default=0, type=int)
    frm = request.args.get("from")
    to = request.args.get("to")

    where, params = ["code = %s"], [code]
    if frm:
        where.append("effective_from >= %s")
        params.append(frm)
    if to:
        where.append("effective_from < %s::timestamp + interval '1 day'")
        params.append(to)

    where_sql = "WHERE " + " AND ".join(where)

    # Safe: where_sql contains only string constants and %s placeholders.
    # User data is passed via params to cur.execute(), not concatenated into SQL.
    # nosemgrep: python.flask.security.injection.tainted-sql-string.tainted-sql-string
    sql = """
          SELECT price_rub, effective_from, effective_to
          FROM product_prices
          {}
          ORDER BY effective_from DESC
          LIMIT %s OFFSET %s
        """.format(where_sql)

    with (
        get_db() as conn,
        conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur,
    ):
        cur.execute(sql, (*params, limit, offset))
        rows = cur.fetchall()
    return jsonify({"code": code, "items": rows, "limit": limit, "offset": offset})


@app.route("/sku/<code>/inventory-history", methods=["GET"])
@limiter.limit(os.getenv("RATE_LIMIT_PROTECTED", "1000/hour"))
@require_api_key
def inventory_history(code: str):
    """
    Get inventory history for SKU
    ---
    tags:
      - Products
    summary: Get historical inventory changes
    description: |
      Returns inventory history from inventory_history table.
      **Requires API key authentication.**
    security:
      - ApiKeyAuth: []
    parameters:
      - name: code
        in: path
        type: string
        required: true
        description: Product SKU code
        example: "D011283"
      - name: from
        in: query
        type: string
        format: date
        required: false
        description: Start date (YYYY-MM-DD)
        example: "2025-01-01"
      - name: to
        in: query
        type: string
        format: date
        required: false
        description: End date (YYYY-MM-DD)
        example: "2025-01-31"
      - name: limit
        in: query
        type: integer
        required: false
        default: 50
        description: Maximum number of records
        example: 50
      - name: offset
        in: query
        type: integer
        required: false
        default: 0
        description: Number of records to skip
        example: 0
    responses:
      200:
        description: Inventory history records
        schema:
          type: object
          properties:
            code:
              type: string
            items:
              type: array
              items:
                type: object
                properties:
                  stock_total:
                    type: integer
                  reserved:
                    type: integer
                  stock_free:
                    type: integer
                  as_of:
                    type: string
                    format: date-time
            limit:
              type: integer
            offset:
              type: integer
        examples:
          application/json: {
            "code": "D011283",
            "items": [
              {
                "stock_total": 48,
                "reserved": 5,
                "stock_free": 43,
                "as_of": "2025-01-20T12:00:00"
              },
              {
                "stock_total": 52,
                "reserved": 3,
                "stock_free": 49,
                "as_of": "2025-01-15T12:00:00"
              }
            ],
            "limit": 50,
            "offset": 0
          }
      403:
        description: Forbidden - invalid or missing API key
    """
    limit = request.args.get("limit", default=50, type=int)
    offset = request.args.get("offset", default=0, type=int)
    frm = request.args.get("from")
    to = request.args.get("to")

    where, params = ["code = %s"], [code]
    if frm:
        where.append("as_of >= %s")
        params.append(frm)
    if to:
        where.append("as_of < %s::timestamp + interval '1 day'")
        params.append(to)

    where_sql = "WHERE " + " AND ".join(where)

    # Safe: where_sql contains only string constants and %s placeholders.
    # User data is passed via params to cur.execute(), not concatenated into SQL.
    # nosemgrep: python.flask.security.injection.tainted-sql-string.tainted-sql-string
    sql = """
          SELECT stock_total, reserved, stock_free, as_of
          FROM inventory_history
          {}
          ORDER BY as_of DESC
          LIMIT %s OFFSET %s
        """.format(where_sql)

    with (
        get_db() as conn,
        conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur,
    ):
        cur.execute(sql, (*params, limit, offset))
        rows = cur.fetchall()
    return jsonify({"code": code, "items": rows, "limit": limit, "offset": offset})


if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    port = int(os.getenv("FLASK_PORT", "8000"))
    app.run(host=host, port=port, debug=debug)
