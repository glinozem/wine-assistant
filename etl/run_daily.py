import argparse
import os
import re
from datetime import date, datetime, time, timezone

import pandas as pd
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

try:
    # when imported as a module: python -m scripts.run_import_orchestrator / tests / etc.
    from .utils import norm_str, normalize_volume, parse_abv, to_number
except ImportError:
    # backward-compat: when run as a script from etl/ directory
    from utils import norm_str, normalize_volume, parse_abv, to_number


load_dotenv()


def get_conn():
    return psycopg2.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=int(os.getenv("PGPORT", "5432")),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", "postgres"),
        dbname=os.getenv("PGDATABASE", "wine_db"),
    )


def norm_supplier_key(x) -> str | None:
    if x is None:
        return None
    s = str(x).strip()
    if not s or s == "_":
        return None
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or None


def upsert_product(cur, row, *, effective_from: datetime):
    # products: master data + current prices (for UI/API)
    sql = """
    INSERT INTO products (
        code, supplier, producer, title_ru, title_en, country, region,
        color, style, grapes, abv, pack, volume,
        price_list_rub, price_final_rub, price_rub
    )
    VALUES (
        %(code)s, %(supplier)s, %(producer)s, %(title_ru)s, %(title_en)s, %(country)s, %(region)s,
        %(color)s, %(style)s, %(grapes)s, %(abv)s, %(pack)s, %(volume)s,
        %(price_list_rub)s, %(price_final_rub)s, %(price_rub)s
    )
    ON CONFLICT (code) DO UPDATE SET
      supplier=COALESCE(EXCLUDED.supplier, products.supplier),
      producer=EXCLUDED.producer,
      title_ru=EXCLUDED.title_ru,
      title_en=EXCLUDED.title_en,
      country=EXCLUDED.country,
      region=EXCLUDED.region,
      color=EXCLUDED.color,
      style=EXCLUDED.style,
      grapes=EXCLUDED.grapes,
      abv=EXCLUDED.abv,
      pack=EXCLUDED.pack,
      volume=EXCLUDED.volume,
      price_list_rub=COALESCE(EXCLUDED.price_list_rub, products.price_list_rub),
      price_final_rub=COALESCE(EXCLUDED.price_final_rub, products.price_final_rub),
      price_rub=COALESCE(EXCLUDED.price_rub, products.price_rub);
    """
    cur.execute(sql, row)

    # product_prices: history (close previous open interval if price changed)
    price = row.get("price_rub")
    if price is None:
        return

    cur.execute(
        """SELECT price_rub
           FROM product_prices
          WHERE code=%s AND effective_to IS NULL
          ORDER BY effective_from DESC
          LIMIT 1""",
        (row["code"],),
    )
    last = cur.fetchone()
    last_price = None if last is None else float(last[0])

    if last_price is None or abs(last_price - float(price)) > 1e-9:
        if last is not None:
            cur.execute(
                """UPDATE product_prices
                       SET effective_to=%s
                     WHERE code=%s AND effective_to IS NULL""",
                (effective_from, row["code"]),
            )
        cur.execute(
            """INSERT INTO product_prices (code, price_rub, effective_from, effective_to)
                 VALUES (%s, %s, %s, NULL)""",
            (row["code"], float(price), effective_from),
        )


def upsert_inventory(cur, row, *, as_of: datetime):
    """Upsert inventory snapshot into `inventory` and append a same-day snapshot to `inventory_history` (idempotent)."""
    code = row.get("code")
    if not code:
        return

    stock_total = row.get("stock_total")
    reserved = row.get("reserved")
    stock_free = row.get("stock_free")

    if stock_total is None and reserved is None and stock_free is None:
        return

    # inventory table columns are NOT NULL => default missing values to 0
    if stock_total is None:
        stock_total = 0
    if reserved is None:
        reserved = 0
    if stock_free is None:
        stock_free = 0

    # Normalize as_of for consistent timestamptz writes
    as_of_ts = as_of.astimezone(timezone.utc) if as_of.tzinfo else as_of.replace(tzinfo=timezone.utc)

    cur.execute(
        """INSERT INTO inventory (code, stock_total, reserved, stock_free, asof_date)
             VALUES (%s, %s, %s, %s, %s)
             ON CONFLICT (code) DO UPDATE SET
                 stock_total=EXCLUDED.stock_total,
                 reserved=EXCLUDED.reserved,
                 stock_free=EXCLUDED.stock_free,
                 asof_date=EXCLUDED.asof_date,
                 updated_at=now()""",
        (code, stock_total, reserved, stock_free, as_of.date()),
    )
    # Snapshot into inventory_history (idempotent); keep only meaningful stock rows to avoid noise.
    if float(stock_total) != 0 or float(reserved) != 0 or float(stock_free) != 0:
        cur.execute(
            """INSERT INTO inventory_history (as_of, code, stock_total,
                                              reserved, stock_free)
               SELECT %s,
                      %s,
                      %s,
                      %s,
                      %s WHERE NOT EXISTS (
                 SELECT 1
                   FROM inventory_history h
                  WHERE h.code = %s
                   AND h.as_of:: date = %s:: date
                   )""",
            (as_of_ts, code, stock_total, reserved, stock_free, code,
             as_of_ts),
        )

def _norm_col(x) -> str:
    return str(x).strip().lower().replace("\n", " ")

def detect_mapping(df, mapping_template):
    mt = mapping_template.get("mapping") or {}

    if mt:
        norm_to_actual = {_norm_col(c): c for c in df.columns}
        mapping = {}
        ok = True
        for tgt, expected in mt.items():
            k = _norm_col(expected)
            if k in norm_to_actual:
                mapping[tgt] = norm_to_actual[k]
            else:
                ok = False
                break
        if ok:
            return mapping

    # 2) Fallback: aliases heuristic (as before)
    aliases = {
        "code": ["код", "артикул", "sku", "код товара", "id"],
        "producer": ["производитель", "бренд", "house", "winery", "поставщик"],
        "supplier": ["поставщик", "supplier_key", "supplier"],
        "title_ru": ["наименование", "наим.", "продукт", "вино", "название"],
        "title_en": ["name_en", "title_en", "англ", "en"],
        "country": ["страна"],
        "region": ["регион", "аппел", "апел", "область"],
        "color": ["цвет"],
        "style": ["стиль", "тип", "категория"],
        "grapes": ["сорт", "сорта", "сортовой состав", "виноград"],
        "abv": ["крепость", "алк", "алкоголь", "alc", "abv"],
        "pack": ["упак", "бут", "в кор", "pack", "case"],
        "price_list_rub": ["цена прайс", "прайс", "price list", "list price"],
        "price_final_rub": ["цена со скид", "цена с", "final price", "price final", "цена фин"],
        "price_rub": ["цена", "руб", "price", "стоимость"],
        "stock_total": ["остатки", "остаток", "stock total", "налич", "in stock"],
        "reserved": ["резерв", "reserved"],
        "stock_free": ["свобод", "free", "available", "доступн"],
    }
    mapping = {}
    for tgt, keys in aliases.items():
        for c in df.columns:
            lc = _norm_col(c)
            if any(k in lc for k in keys):
                mapping[tgt] = c
                break
        return mapping


def normalize_row(raw, m):
    # Prices
    price_list = to_number(raw.get(m.get("price_list_rub")))
    price_final = to_number(raw.get(m.get("price_final_rub")))
    price_rub = to_number(raw.get(m.get("price_rub")))

    # Fallbacks: if only one of the price columns is mapped
    if price_final is None and price_rub is not None:
        price_final = price_rub
    if price_rub is None and price_final is not None:
        price_rub = price_final

    # Inventory
    stock_total = to_number(raw.get(m.get("stock_total")))
    reserved = to_number(raw.get(m.get("reserved")))
    stock_free = to_number(raw.get(m.get("stock_free")))

    # If "free" is missing but total/reserved exist, compute it
    if stock_free is None and stock_total is not None and reserved is not None:
        stock_free = max(0.0, stock_total - reserved)

    supplier_src = raw.get(m.get("supplier")) if m.get("supplier") else None
    if supplier_src is None:
        supplier_src = raw.get(m.get("producer"))

    supplier_key = norm_str(supplier_src)

    producer_src = raw.get(m.get("producer")) if m.get("producer") else None
    if producer_src is None:
        producer_src = supplier_src

    return dict(
        code=str(raw.get(m.get("code"))).strip() if raw.get(m.get("code")) is not None else None,
        supplier=supplier_key,
        producer=norm_str(producer_src) or supplier_key,
        title_ru=norm_str(raw.get(m.get("title_ru"))),
        title_en=norm_str(raw.get(m.get("title_en"))),
        country=norm_str(raw.get(m.get("country"))),
        region=norm_str(raw.get(m.get("region"))),
        color=norm_str(raw.get(m.get("color"))),
        style=norm_str(raw.get(m.get("style"))),
        grapes=norm_str(raw.get(m.get("grapes"))),
        abv=parse_abv(raw.get(m.get("abv"))),
        volume=normalize_volume(raw.get(m.get("volume"))),
        pack=to_number(raw.get(m.get("pack"))),

        price_list_rub=price_list,
        price_final_rub=price_final,
        price_rub=price_rub,

        stock_total=stock_total,
        reserved=reserved,
        stock_free=stock_free,
    )


def is_valid(row):
    return bool(row["code"] and row["title_ru"] and (row["price_rub"] is not None))


def run_etl(
    xlsx_path=None,
    csv_path=None,
    sheet=None,
    mapping_path=None,
    conn=None,
    *,
    as_of_date: date | None = None,
    as_of_datetime: datetime | None = None,
):
    effective_from = as_of_datetime
    if effective_from is None and as_of_date is not None:
        effective_from = datetime.combine(as_of_date, time.min)
    if effective_from is None:
        effective_from = datetime.utcnow()

    mapping_template = {}

    if not mapping_path:
        mapping_path = "etl/mapping_template.json"

    if mapping_path and os.path.exists(mapping_path):
        import json

        with open(mapping_path, "r", encoding="utf-8") as f:
            mapping_template = json.load(f)

    header_row = mapping_template.get("header_row", 0)
    if not isinstance(header_row, int) or header_row < 0:
        header_row = 0

    if not sheet and mapping_template.get("sheet"):
        sheet = mapping_template["sheet"]

    frames = []
    if xlsx_path and os.path.exists(xlsx_path):
        if sheet:
            df = pd.read_excel(xlsx_path, sheet_name=sheet, header=header_row)
            frames.append(df)
        else:
            xls = pd.ExcelFile(xlsx_path)
            for s in xls.sheet_names:
                try:
                    frames.append(pd.read_excel(xlsx_path, sheet_name=s, header=header_row))
                except Exception:
                    pass
    elif csv_path and os.path.exists(csv_path):
        frames.append(pd.read_csv(csv_path))

    if not frames:
        raise SystemExit("No input data found")

    first = next((f for f in frames if not f.empty), None)
    mapping = detect_mapping(first, mapping_template)

    rows = []

    total_input_rows = sum(int(len(df)) for df in frames if df is not None)

    for df in frames:
        for _, r in df.iterrows():
            row = normalize_row(r, mapping)
            if is_valid(row):
                rows.append(row)

    processed_rows = len(rows)
    rows_skipped = max(0, total_input_rows - processed_rows)

    # Если входные данные есть, но валидных строк 0 — это почти всегда сломанный mapping/sheet.
    if total_input_rows > 0 and processed_rows == 0:
        raise RuntimeError(
            "ETL produced 0 valid rows. Check sheet name and mapping_template.json (columns mismatch)."
        )

    own_conn = conn is None
    if own_conn:
        conn = get_conn()

    try:
        with conn.cursor() as cur:
            for row in rows:
                upsert_product(cur, row, effective_from=effective_from)
                upsert_inventory(cur, row, as_of=effective_from)

        # коммитим только если это наш conn; если conn orchestrator'а — он решает commit/rollback
        if own_conn:
            conn.commit()
    finally:
        if own_conn:
            conn.close()

    metrics = {
        "rows_skipped": rows_skipped,
        "input_rows_total": total_input_rows,
        "processed_rows": processed_rows,
        "sheet": sheet,
        "mapping_path": mapping_path,
        "mapping_keys": sorted(list(mapping.keys())) if isinstance(mapping, dict) else [],
    }

    print(f"ETL completed: processed={processed_rows}")

    return {"metrics": metrics, "artifact_paths": {}}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", help="Path to daily Excel file")
    ap.add_argument("--csv", help="Fallback CSV path", default="data/sample/dw_sample_products.csv")
    ap.add_argument("--sheet", help="Specific sheet name")
    ap.add_argument("--mapping", help="Mapping JSON path", default="etl/mapping_template.json")
    args = ap.parse_args()
    run_etl(args.xlsx, args.csv, args.sheet, args.mapping)
