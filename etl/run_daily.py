import argparse
import os
from datetime import date, datetime, time

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


def upsert_product(cur, row, *, effective_from: datetime):
    sql = """
    INSERT INTO products (code, producer, title_ru, title_en, country, region,
                          color, style, grapes, abv, pack, volume, price_rub)
    VALUES (%(code)s, %(producer)s, %(title_ru)s, %(title_en)s, %(country)s, %(region)s,
            %(color)s, %(style)s, %(grapes)s, %(abv)s, %(pack)s, %(volume)s, %(price_rub)s)
    ON CONFLICT (code) DO UPDATE SET
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
      price_rub=EXCLUDED.price_rub;
    """
    cur.execute(sql, row)

    cur.execute(
        """
        SELECT price_rub FROM product_prices
        WHERE code=%s AND effective_to IS NULL
        ORDER BY effective_from DESC
        LIMIT 1
        """,
        (row["code"],),
    )
    last = cur.fetchone()

    if last is None or float(last[0]) != float(row["price_rub"] or 0):
        # 1) закрываем текущую открытую цену
        cur.execute(
            """
            UPDATE product_prices
            SET effective_to = %s
            WHERE code=%s AND effective_to IS NULL
            """,
            (effective_from, row["code"]),
        )
        # 2) вставляем новую цену с effective_from
        cur.execute(
            """
            INSERT INTO product_prices (code, price_rub, effective_from)
            VALUES (%s, %s, %s)
            """,
            (row["code"], row["price_rub"], effective_from),
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
        "title_ru": ["наименование", "наим.", "продукт", "вино", "название"],
        "title_en": ["name_en", "title_en", "англ", "en"],
        "country": ["страна"],
        "region": ["регион", "аппел", "апел", "область"],
        "color": ["цвет"],
        "style": ["стиль", "тип", "категория"],
        "grapes": ["сорт", "сорта", "сортовой состав", "виноград"],
        "abv": ["крепость", "алк", "алкоголь", "alc", "abv"],
        "pack": ["упаковка", "коробке", "кол-во"],
        "volume": ["объем", "объём", "емк", "емкость", "литраж", "тара"],
        "price_rub": ["цена", "цена руб", "цена, руб", "цена (руб)", "стоимость", "опт"],
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
    row = {
        "code": norm_str(raw.get(m.get("code"))),
        "producer": norm_str(raw.get(m.get("producer"))),
        "title_ru": norm_str(raw.get(m.get("title_ru"))),
        "title_en": norm_str(raw.get(m.get("title_en"))),
        "country": norm_str(raw.get(m.get("country"))),
        "region": norm_str(raw.get(m.get("region"))),
        "color": norm_str(raw.get(m.get("color"))),
        "style": norm_str(raw.get(m.get("style"))),
        "grapes": norm_str(raw.get(m.get("grapes"))),
        "abv": parse_abv(raw.get(m.get("abv"))),
        "pack": norm_str(raw.get(m.get("pack"))),
        "volume": normalize_volume(raw.get(m.get("volume"))),
        "price_rub": to_number(raw.get(m.get("price_rub"))),
    }
    return row


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
