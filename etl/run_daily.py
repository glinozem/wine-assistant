import argparse
import os

import pandas as pd
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
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


def upsert_product(cur, row):
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
        ORDER BY effective_from DESC LIMIT 1
    """,
        (row["code"],),
    )
    last = cur.fetchone()
    if last is None or float(last[0]) != float(row["price_rub"] or 0):
        cur.execute(
            """
            UPDATE product_prices SET effective_to = now()
            WHERE code=%s AND effective_to IS NULL
        """,
            (row["code"],),
        )
        cur.execute(
            """
            INSERT INTO product_prices (code, price_rub) VALUES (%s, %s)
        """,
            (row["code"], row["price_rub"]),
        )


def detect_mapping(df, mapping_template):
    mt = mapping_template.get("mapping") or {}
    if mt and all(str(v) in df.columns for v in mt.values()):
        return {k: v for k, v in mt.items() if v in df.columns}

    aliases = {
        "code": ["код", "артикул", "sku", "код товара", "id"],
        "producer": ["производитель", "бренд", "house", "winery"],
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
        "price_rub": [
            "цена",
            "цена руб",
            "цена, руб",
            "цена (руб)",
            "стоимость",
            "опт",
        ],
    }
    mapping = {}
    for tgt, keys in aliases.items():
        for c in df.columns:
            lc = str(c).strip().lower()
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


def run_etl(xlsx_path=None, csv_path=None, sheet=None, mapping_path=None):
    mapping_template = {}
    if mapping_path and os.path.exists(mapping_path):
        import json

        with open(mapping_path, "r", encoding="utf-8") as f:
            mapping_template = json.load(f)

    frames = []
    if xlsx_path and os.path.exists(xlsx_path):
        if sheet:
            df = pd.read_excel(xlsx_path, sheet_name=sheet)
            frames.append(df)
        else:
            xls = pd.ExcelFile(xlsx_path)
            for s in xls.sheet_names:
                try:
                    frames.append(pd.read_excel(xlsx_path, sheet_name=s))
                except Exception:
                    pass
    elif csv_path and os.path.exists(csv_path):
        frames.append(pd.read_csv(csv_path))

    if not frames:
        raise SystemExit("No input data found")

    first = next((f for f in frames if not f.empty), None)
    mapping = detect_mapping(first, mapping_template)

    rows = []
    for df in frames:
        for _, r in df.iterrows():
            row = normalize_row(r, mapping)
            if is_valid(row):
                rows.append(row)

    with get_conn() as conn, conn.cursor() as cur:
        for row in rows:
            upsert_product(cur, row)
        conn.commit()
    print(f"ETL completed: processed={len(rows)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", help="Path to daily Excel file")
    ap.add_argument("--csv", help="Fallback CSV path", default="data/sample/dw_sample_products.csv")
    ap.add_argument("--sheet", help="Specific sheet name")
    ap.add_argument("--mapping", help="Mapping JSON path", default="etl/mapping_template.json")
    args = ap.parse_args()
    run_etl(args.xlsx, args.csv, args.sheet, args.mapping)
