# api/app.py

import os
from functools import wraps

from flask import Flask, request, jsonify
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# JSON всегда в UTF-8 без \uXXXX
app.json.ensure_ascii = False           # Flask ≥ 2.2
app.config["JSON_AS_ASCII"] = False     # совместимость


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


def get_conn():
    return psycopg2.connect(
        host=os.getenv("PGHOST", "127.0.0.1"),
        port=int(os.getenv("PGPORT", "5432")),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", "postgres"),
        dbname=os.getenv("PGDATABASE", "wine_db"),
    )


@app.get("/health")
def health():
    return jsonify(ok=True)


@app.get("/sku/<code>")
@require_api_key
def get_sku(code: str):
    """
    Карточка SKU.
    Возвращает всю строку products (включая price_list_rub/price_final_rub/title_en)
    и current_price из product_prices (текущая открытая цена, если ведется история).
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
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (code,))
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "not_found"}), 404
        return jsonify(row)


@app.get("/search")
def search():
    """
    Поиск по каталогу.
    Фильтрация по ФИНАЛЬНОЙ цене (price_final_rub).
    Поисковый запрос q:
      - добавляем ILIKE по p.search_text и p.title_en (fallback для латиницы/кириллицы)
      - сортируем по similarity(p.search_text, q) без жесткого отсечения порогом
    Возвращаем обе цены: price_list_rub и price_final_rub.
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

    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SET pg_trgm.similarity_threshold = 0.1;")
        cur.execute(sql, (*params, *order_params, limit))
        rows = cur.fetchall()

    return jsonify({"items": rows, "query": q})


@app.get("/catalog/search")
def catalog_search():
    """
    Расширенный поиск с пагинацией и остатками.
    Фильтрация по ФИНАЛЬНОЙ цене (price_final_rub).
    По q: ILIKE по search_text/title_en + сортировка по similarity без жесткого порога.
    Возвращаем обе цены и вычисляемые поля остатков.
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
        where.append("p.price_final_rub <= %s"); params.append(max_price)
    if color:
        where.append("p.color ILIKE %s");  params.append(f"%{color}%")
    if region:
        where.append("p.region ILIKE %s"); params.append(f"%{region}%")
    if style:
        where.append("p.style ILIKE %s");  params.append(f"%{style}%")
    if grape:
        where.append("p.grapes ILIKE %s"); params.append(f"%{grape}%")

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

    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SET pg_trgm.similarity_threshold = 0.1;")
        cur.execute(sql, (*params, *order_params, limit, offset))
        rows = cur.fetchall()

    total = rows[0]["total_count"] if rows else 0
    for r in rows:
        r.pop("total_count", None)

    return jsonify({"items": rows, "total": total, "limit": limit, "offset": offset, "query": q})


if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    port = int(os.getenv("FLASK_PORT", "8000"))
    app.run(host=host, port=port, debug=debug)
