#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import re
import csv
import sys
import argparse
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()


# -------------------------------
# DB connection
# -------------------------------
def get_conn():
    return psycopg2.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=int(os.getenv("PGPORT", "5432")),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", "postgres"),
        dbname=os.getenv("PGDATABASE", "wine_db"),
    )


# -------------------------------
# CSV helpers
# -------------------------------
def sniff_encoding(head_bytes: bytes) -> str:
    """Pick a sensible encoding for a text file header."""
    for enc in ("utf-8", "utf-8-sig", "cp1251", "latin1"):
        try:
            head_bytes.decode(enc, errors="strict")
            return enc
        except UnicodeDecodeError:
            continue
    return "latin1"


def choose_sep_robust(path: str, enc: str) -> str:
    """
    Try multiple separators and pick the one that yields the
    'widest' consistent table on a small sample.
    """
    candidates = [",", ";", "\t", "|"]
    best = (0, 0, ",")  # (n_cols, n_rows, sep)

    for sep in candidates:
        try:
            sample = pd.read_csv(
                path,
                sep=sep,
                engine="python",
                encoding=enc,
                nrows=400,
                on_bad_lines="skip",
                dtype=str,
                quotechar='"',
                escapechar="\\",
            )
            score = (sample.shape[1], sample.shape[0])
            if score > best[:2]:
                best = (score[0], score[1], sep)
        except Exception:
            continue

    # As a fallback, try csv.Sniffer on the header
    if best[0] == 0:
        try:
            with open(path, "rb") as fb:
                head = fb.read(4096).decode(enc, errors="ignore")
            dialect = csv.Sniffer().sniff(head, delimiters=[",", ";", "\t", "|"])
            return dialect.delimiter
        except Exception:
            return ","
    return best[2]


def read_products_csv(path: str, sep_choice: str = "auto", enc_choice: str = "auto") -> pd.DataFrame:
    """
    Robust CSV reader:
    - auto encoding (utf-8 / utf-8-sig / cp1251 / latin1)
    - auto separator (',',';','\\t','|') or user-provided via --sep
    - tolerant parsing (skips bad lines; logs warning)
    - trims whitespace; keeps all columns as strings
    """
    # Read small header to guess encoding
    with open(path, "rb") as fb:
        head_bytes = fb.read(4096)

    enc = sniff_encoding(head_bytes) if enc_choice == "auto" else enc_choice
    if sep_choice == "auto":
        sep = choose_sep_robust(path, enc)
    else:
        sep = "\t" if sep_choice == "\\t" else sep_choice

    df = pd.read_csv(
        path,
        sep=sep,
        engine="python",
        encoding=enc,
        quotechar='"',
        escapechar="\\",
        on_bad_lines="skip",  # don't crash on malformed lines
        dtype=str,            # keep raw strings; normalize later
    )

    # Normalize headers and trim cells
    df.columns = [str(c).strip() for c in df.columns]
    for c in df.columns:
        if df[c].dtype == object:
            df[c] = df[c].str.strip()

    print(f"[read_csv] encoding={enc}, sep={repr(sep)}, rows={len(df)}, cols={len(df.columns)}")
    return df


# -------------------------------
# Normalization helpers
# -------------------------------
def to_float_price(x):
    if x is None:
        return None
    s = str(x).strip()
    if s == "" or s.lower() in {"nan", "none", "null", "-"}:
        return None
    # remove NBSP and spaces, currency signs and non-numerics (keep . , -)
    s = s.replace("\u00a0", "").replace(" ", "")
    s = re.sub(r"[^\d,.\-]", "", s)
    # convert decimal comma to dot if no dot present
    if s.count(",") == 1 and s.count(".") == 0:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ensure required columns present; map possible alt names; cast/clean values.
    """
    # Optional mapping from alternative headers (ru/en variants) to canonical names
    rename_map = {
        "артикул": "code",
        "код": "code",
        "производитель": "producer",
        "название_ru": "title_ru",
        "название": "title_ru",
        "название_en": "title_en",
        "страна": "country",
        "регион": "region",
        "цвет": "color",
        "стиль": "style",
        "сорт": "grapes",
        "сорта": "grapes",
        "крепость": "abv",
        "тара": "pack",
        "объем": "volume",
        "объём": "volume",
        "объем, л": "volume",
        "цена": "price_rub",
        "цена_руб": "price_rub",
        "price": "price_rub",
    }

    # Lowercase-safe rename for any localized headers
    lower_cols = {c: c.lower().strip() for c in df.columns}
    df.rename(columns=lower_cols, inplace=True)
    df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns}, inplace=True)

    expected = [
        "code",
        "producer",
        "title_ru",
        "title_en",
        "country",
        "region",
        "color",
        "style",
        "grapes",
        "abv",
        "pack",
        "volume",
        "price_rub",
    ]
    for col in expected:
        if col not in df.columns:
            df[col] = None

    # keep only expected columns and replace NaN -> None
    df = df[expected]
    df = df.where(pd.notnull(df), None)

    # normalize price and abv
    df["price_rub"] = df["price_rub"].map(to_float_price)
    if "abv" in df.columns:
        def _norm_abv(x):
            if x is None:
                return None
            s = str(x).strip().replace("%", "")
            s = s.replace(",", ".")
            return s if s else None
        df["abv"] = df["abv"].map(_norm_abv)

    return df


# -------------------------------
# Main
# -------------------------------
def main():
    ap = argparse.ArgumentParser(description="Load products CSV into Postgres (upsert by code).")
    ap.add_argument("--csv", required=True, help="Path to the CSV file")
    ap.add_argument("--sep", default="auto", choices=[",", ";", "\\t", "|", "auto"],
                    help="Field separator: ',', ';', '\\t', '|' or 'auto' (default)")
    ap.add_argument("--encoding", default="auto",
                    help="File encoding or 'auto' (default). Examples: utf-8, cp1251")
    ap.add_argument("--batch", type=int, default=1000, help="Batch size for inserts (default: 1000)")
    args = ap.parse_args()

    df = read_products_csv(args.csv, sep_choice=args.sep, enc_choice=args.encoding)
    df = normalize_df(df)

    rows = [
        (
            r["code"], r["producer"], r["title_ru"], r["title_en"], r["country"],
            r["region"], r["color"], r["style"], r["grapes"], r["abv"],
            r["pack"], r["volume"], r["price_rub"]
        )
        for _, r in df.iterrows()
        if r.get("code")  # ignore rows without a code
    ]

    if not rows:
        print("No rows to load (empty or no valid 'code' values).")
        sys.exit(0)

    sql = """
    INSERT INTO products (
        code, producer, title_ru, title_en, country, region,
        color, style, grapes, abv, pack, volume, price_rub
    )
    VALUES %s
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

    try:
        with get_conn() as conn, conn.cursor() as cur:
            execute_values(cur, sql, rows, page_size=args.batch)
            conn.commit()
        print(f"CSV loaded: inserted/updated {len(rows)} rows")
    except psycopg2.errors.UndefinedObject as e:
        # Likely ON CONFLICT target not present (no unique index on products.code)
        print("ERROR: ON CONFLICT needs a unique constraint on products(code). "
              "Run this once in DB:\n  ALTER TABLE products "
              "ADD CONSTRAINT products_code_key UNIQUE (code);")
        raise
    except Exception:
        print("ERROR: load failed.")
        raise


if __name__ == "__main__":
    main()
