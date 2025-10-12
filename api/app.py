# api/app.py
import os
import json
from functools import wraps

from flask import Flask, request, jsonify, Response
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

# Кириллица без \uXXXX
app.json.ensure_ascii = False
app.config["JSON_AS_ASCII"] = False

API_KEY = os.getenv("API_KEY")
PROTECT_CATALOG = os.getenv("PROTECT_CATALOG", "0") == "1"

# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def require_api_key(f):
    @wraps(f)
    def wrapped(*a, **kw):
        if API_KEY and (request.headers.get("X-API-Key") != API_KEY):
            return jsonify(error="forbidden"), 403
        return f(*a, **kw)
    return wrapped

def maybe_protected(f):
    """Вешает require_api_key на эндпоинт, если PROTECT_CATALOG=1"""
    return require_api_key(f) if PROTECT_CATALOG else f

def get_conn():
    return psycopg2.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=int(os.getenv("PGPORT", "5432")),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", "postgres"),
        dbname=os.getenv("PGDATABASE", "wine_db"),
    )

def clamp(n, lo, hi):
    return max(lo, min(hi, n))

# ---------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------
@app.get("/health")
def health():
    return jsonify(ok=True)

@app.get("/sku/<code>")
@require_api_key
def get_sku(code):
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT p.*, pp.price_rub AS current_price
            FROM products p
            LEFT JOIN LATERAL (
                SELECT price_rub
                FROM product_prices
                WHERE code = p.code AND effective_to IS NULL
                ORDER BY effective_from DESC
                LIMIT 1
            ) pp ON TRUE
            WHERE p.code = %s
            """,
            (code,),
        )
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "not_found"}), 404
        return jsonify(row)

@app.get("/search")
def search():
    q = (request.args.get("q") or "").strip()
    max_price = request.args.get("max_price", type=float)
    color = request.args.get("color")
    region = request.args.get("region")
    style = request.args.get("style")
    limit = clamp(request.args.get("limit", default=10, type=int), 1, 100)

    where, params = [], []
    if max_price is not None:
        where.append("p.price_rub <= %s"); params.append(max_price)
    if color:
        where.append("p.color ILIKE %s");  params.append(f"%{color}%")
    if region:
        where.append("p.region ILIKE %s"); params.append(f"%{region}%")
    if style:
        where.append("p.style ILIKE %s");  params.append(f"%{style}%")
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SET pg_trgm.similarity_threshold = 0.1;")
        if q:
            sql = f"""
                SELECT p.code, p.producer, p.title_ru, p.country, p.region, p.color,
                       p.style, p.grapes, p.abv, p.pack, p.volume, p.price_rub,
                       similarity(p.search_text, %s) AS rank
                FROM products p
                {where_sql}
                ORDER BY rank DESC NULLS LAST, p.price_rub ASC
                LIMIT %s
            """
            cur.execute(sql, (*params, q, limit))
        else:
            sql = f"""
                SELECT p.code, p.producer, p.title_ru, p.country, p.region, p.color,
                       p.style, p.grapes, p.abv, p.pack, p.volume, p.price_rub
                FROM products p
                {where_sql}
                ORDER BY p.price_rub ASC, p.code
                LIMIT %s
            """
            cur.execute(sql, (*params, limit))
        rows = cur.fetchall()
    return jsonify({"items": rows, "query": q})

@app.get("/catalog/search")
@maybe_protected
def catalog_search():
    q = (request.args.get("q") or "").strip()
    max_price = request.args.get("max_price", type=float)
    color = request.args.get("color")
    region = request.args.get("region")
    style = request.args.get("style")
    grape = request.args.get("grape")
    in_stock = request.args.get("in_stock", type=str)  # "true"/"false"/None
    limit = clamp(request.args.get("limit", default=20, type=int), 1, 100)
    offset = max(0, request.args.get("offset", default=0, type=int))

    where, params = [], []
    if max_price is not None:
        where.append("p.price_rub <= %s"); params.append(max_price)
    if color:
        where.append("p.color ILIKE %s");  params.append(f"%{color}%")
    if region:
        where.append("p.region ILIKE %s"); params.append(f"%{region}%")
    if style:
        where.append("p.style ILIKE %s");  params.append(f"%{style}%")
    if grape:
        where.append("p.grapes ILIKE %s"); params.append(f"%{grape}%")
    if in_stock in ("true", "false"):
        where.append("coalesce(i.in_stock, true) = %s"); params.append(in_stock == "true")
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SET pg_trgm.similarity_threshold = 0.1;")

        if q:
            sql = f"""
              SELECT p.code, p.producer, p.title_ru, p.country, p.region, p.color, p.style,
                     p.grapes, p.abv, p.pack, p.volume, p.price_rub,
                     coalesce(i.in_stock, true) AS in_stock,
                     COUNT(*) OVER() AS total_count,
                     similarity(p.search_text, %s) AS rank
              FROM products p
              LEFT JOIN inventory i ON i.code = p.code
              {where_sql}
              ORDER BY rank DESC NULLS LAST, p.price_rub ASC
              LIMIT %s OFFSET %s
            """
            cur.execute(sql, (*params, q, limit, offset))
        else:
            sql = f"""
              SELECT p.code, p.producer, p.title_ru, p.country, p.region, p.color, p.style,
                     p.grapes, p.abv, p.pack, p.volume, p.price_rub,
                     coalesce(i.in_stock, true) AS in_stock,
                     COUNT(*) OVER() AS total_count
              FROM products p
              LEFT JOIN inventory i ON i.code = p.code
              {where_sql}
              ORDER BY p.price_rub ASC, p.code
              LIMIT %s OFFSET %s
            """
            cur.execute(sql, (*params, limit, offset))

        rows = cur.fetchall()

    total = rows[0]["total_count"] if rows else 0
    for r in rows:
        r.pop("total_count", None)
        r.pop("rank", None)
    return jsonify({"items": rows, "total": total, "limit": limit, "offset": offset})

# ---------------------------------------------------------------------
if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=8000, debug=debug)
