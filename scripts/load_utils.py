# scripts/load_utils.py

"""
Вспомогательные функции для импорта прайс-листов:
- чтение CSV/XLSX файлов
- нормализация заголовков и значений
- upsert в базу данных
"""

import logging
import math
import os
import re
from datetime import date, datetime
from typing import Any, Dict, Iterable, Optional, Tuple

import openpyxl  # чтение значения скидки из фиксированной ячейки (например, S5)
import pandas as pd
import psycopg2

__all__ = [
    "get_conn",
    "_norm",
    "_norm_key",
    "_to_float",
    "_to_int",
    "_canonicalize_headers",
    "_get_discount_from_cell",
    "_excel_read",
    "_csv_read",
    "read_any",
    "COLMAP",
]

# Date extraction module for automatic date parsing (Issue #81)


# =========================
# DB
# =========================
def get_conn():
    return psycopg2.connect(
        host=os.getenv("PGHOST", "127.0.0.1"),
        port=int(os.getenv("PGPORT", "5432")),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", "postgres"),
        dbname=os.getenv("PGDATABASE", "wine_db"),
    )


# =========================
# Utils
# =========================
def _norm(s: Any) -> str:
    if s is None:
        return ""
    s = str(s).strip()
    s = s.replace("\r", " ").replace("\n", " ")
    s = re.sub(r"\s+", " ", s)
    return s


def _norm_key(s: Any) -> str:
    s = _norm(s).lower()
    s = s.replace("ё", "е")
    s = s.replace("%", " % ")
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^a-z0-9а-я_]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    # частые артефакты мультишапки
    s = s.replace("алк__", "алк_").replace("емк__л", "емк_л")
    # «Цена со скидкой 0%» -> «цена_со_скидкой»
    s = re.sub(r"(цена_со_скидкой)(_?\d+_?)?$", "цена_со_скидкой", s)
    return s


def _to_float(x: Any) -> Optional[float]:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    sx = str(x)
    m = re.search(r"[-+]?\d+(?:[ \d])*(?:[.,]\d+)?", sx)
    if not m:
        return None
    num = m.group(0).replace(" ", "").replace(",", ".")
    try:
        return float(num)
    except Exception:
        return None


def _to_int(x: Any) -> Optional[int]:
    f = _to_float(x)
    return None if f is None else int(round(f))


# Синонимы колонок -> целевые имена
# ВАЖНО: «цена прайс» -> price_rub (списочная), «цена со скидкой» -> price_discount (финальная из файла)
COLMAP: Dict[str, Optional[str]] = {
    # идентификатор
    "код": "code",
    "code": "code",
    "артикул": "code",
    # наименование
    "наименование": "title_ru",
    "наименование_вина": "title_ru",
    "название": "title_ru",
    "title": "title_ru",
    # производитель/страна/регион
    "производитель": "producer",
    "бренд": "producer",
    "страна": "country",
    "country": "country",
    "регион": "region",
    "провинция": "region",
    "область": "region",
    # сорт
    "сорт": "grapes",
    "сорт_винограда": "grapes",
    "виноград": "grapes",
    "grapes": "grapes",
    # алк
    "алк": "abv",
    "алк_%": "abv",
    "алк_": "abv",
    "алкоголь": "abv",
    "abv": "abv",
    # объём
    "емк_л": "volume",
    "емкость": "volume",
    "объем": "volume",
    "объём": "volume",
    "volume_l": "volume",
    # упаковка
    "бут_в_кор": "pack",
    "бут_в_кор_": "pack",
    "упаковка": "pack",
    "короб": "pack",
    "pack": "pack",
    # цены
    "цена_прайс": "price_rub",
    "цена": "price_rub",
    "price": "price_rub",
    "price_rub": "price_rub",
    "цена_со_скидкой": "price_discount",
    # остатки
    "остатки": "stock_total",
    "остаток": "stock_total",
    "резерв": "reserved",
    "свободный_остаток": "stock_free",
    "свободный": "stock_free",
    # игнор
    "unnamed": None,
    "vivino": None,
    "фото": None,
    "сайт": None,
    "категория": None,
    "тип": None,
    "цвет": None,
    "рейтинг": None,
    "поставщик": None,
    "св_во": None,
    "технический_столбец_для_второго_кода_в_случае_его_наличия": None,
}


def _canonicalize_headers(cols: Iterable[str]) -> Dict[str, Optional[str]]:
    """old_col -> canonical_name (или None для игнора)"""
    mapping: Dict[str, Optional[str]] = {}
    for c in cols:
        key = _norm_key(c)
        if key == "" or key.startswith("unnamed"):
            mapping[c] = None
            continue
        # цена со скидкой с процентом в шапке
        if key.startswith("цена_со_скидкой"):
            mapping[c] = "price_discount"
            continue
        if key in COLMAP:
            mapping[c] = COLMAP[key]  # может быть None (игнор)
        else:
            mapping[c] = None
    return mapping


def _find_header_row(xls_path: str, sheet: Any, max_rows: int = 30) -> int:
    """Ищем строку заголовка по наличию ключей ('код'/'code'/'артикул') в первых max_rows строках."""
    df_top = pd.read_excel(xls_path, sheet_name=sheet, header=None, nrows=max_rows, dtype=str)
    for i, row in df_top.iterrows():
        vals = [_norm_key(v) for v in row.values if pd.notna(v)]
        if any(tok in vals for tok in ("код", "code", "артикул")):
            return i
    return 0


def _get_discount_from_cell(xls_path: str, sheet: Any, cell_addr: str = "S5") -> Optional[float]:
    """
    Возвращает скидку из указанной ячейки как долю (0..1) или None.
    sheet — индекс (int) или имя (str).
    """
    try:
        wb = openpyxl.load_workbook(xls_path, data_only=True, read_only=True)
        ws = wb.worksheets[sheet] if isinstance(sheet, int) else wb[str(sheet)]
        raw = ws[cell_addr].value
        if raw is None:
            return None
        s = str(raw).strip().replace(",", ".")
        if s.endswith("%"):
            v = float(s[:-1].strip()) / 100.0
        else:
            v = float(s)
            if v > 1.0:  # 10 -> 0.10
                v = v / 100.0
        return v if 0.0 <= v <= 1.0 else None
    except Exception:
        return None


# =========================
# Reading CSV/Excel
# =========================
def _excel_read(
    path: str,
    sheet: Any,
    header: Optional[int],
) -> Tuple[pd.DataFrame, int, bool, Optional[float]]:
    """
    Читает Excel. Возвращает (df, header_row_base, used_two_rows, discount_pct_from_header)
    Если в строке ниже шапки видим проценты ('0%'), читаем header=[hdr,hdr+1] и считаем, что в шапке указан % скидки.
    """
    # sheet -> индекс или имя
    try:
        sh = int(sheet) if sheet not in (None, "") else 0
    except ValueError:
        sh = sheet if sheet not in (None, "") else 0

    # базовая строка заголовка
    hdr_base = _find_header_row(path, sh) if header is None else header

    # посмотреть следующую строку
    peek = pd.read_excel(path, sheet_name=sh, header=None, nrows=hdr_base + 2, dtype=str)
    second = peek.iloc[hdr_base + 1] if len(peek.index) > hdr_base + 1 else None
    use_two_rows = False
    disc_hdr: Optional[float] = None

    if second is not None:
        vals = [(_norm(v) or "") for v in second.values]
        if any(re.match(r"^\s*\d+\s*%$", v) for v in vals):
            use_two_rows = True

    if use_two_rows:
        df_raw = pd.read_excel(path, sheet_name=sh, header=[hdr_base, hdr_base + 1], dtype=str)
        # расплющим мультишапку и соберём % скидки, если он указан во второй строке под «Цена со скидкой»
        flat_cols = []
        if isinstance(df_raw.columns, pd.MultiIndex):
            for top, bottom in df_raw.columns:
                top_s = _norm(top)
                bot_s = _norm(bottom)
                label = top_s if (bot_s in ("", "nan", None)) else f"{top_s} {bot_s}"
                flat_cols.append(label)
                # скидка в шапке?
                if _norm_key(top_s) == "цена_со_скидкой" and re.match(r"^\d+\s*%$", bot_s or ""):
                    try:
                        disc_hdr = int(re.sub(r"[^\d]", "", bot_s)) / 100.0
                    except Exception:
                        disc_hdr = None
            df = df_raw.copy()
            df.columns = flat_cols
        else:
            df = df_raw.copy()
    else:
        df = pd.read_excel(path, sheet_name=sh, header=hdr_base, dtype=str)

    print(
        f"[excel] sheet={sh!r}, header_row={'[{},{}]'.format(hdr_base, hdr_base + 1) if use_two_rows else hdr_base}, "
        f"header_discount={disc_hdr}, columns={list(df.columns)}"
    )
    return df, hdr_base, use_two_rows, disc_hdr


def _csv_read(path: str, sep: Optional[str]) -> Tuple[pd.DataFrame, str]:
    if sep is None:
        with open(path, "rb") as fb:
            head = fb.read(4096)
        enc = None
        for enc_try in ("utf-8", "utf-8-sig", "cp1251", "latin1"):
            try:
                head.decode(enc_try)
                enc = enc_try
                break
            except UnicodeDecodeError:
                continue
        if enc is None:
            enc = "latin1"
        import csv as _csv

        try:
            dialect = _csv.Sniffer().sniff(
                head.decode(enc, errors="ignore"), delimiters=[",", ";", "\t", "|"]
            )
            sep = dialect.delimiter
        except Exception:
            sep = ","
        df = pd.read_csv(
            path, sep=sep, engine="python", encoding=enc, dtype=str, on_bad_lines="warn"
        )
        print(f"[csv] encoding={enc}, sep='{sep}', columns={list(df.columns)}")
    else:
        df = pd.read_csv(path, sep=sep, engine="python", dtype=str, on_bad_lines="warn")
        print(f"[csv] sep='{sep}', columns={list(df.columns)}")
    return df, sep  # type: ignore[return-value]


def read_any(
    path: str,
    sep: Optional[str] = None,
    sheet: Any = None,
    header: Optional[int] = None,
) -> pd.DataFrame:
    """
    Excel:
      - авто-поиск строки заголовка
      - если следующая строка содержит проценты (например '0%') под «Цена со скидкой», читаем header=[hdr,hdr+1]
        и сохраняем скидку из шапки в df.attrs['discount_pct_header']
    CSV:
      - авто-энкодинг и разделитель
    """
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xlsm", ".xls"):
        df, hdr_base, used_two_rows, disc_hdr = _excel_read(path, sheet, header)
        # нормализуем названия и маппим
        df.columns = [_norm(c) for c in df.columns]
        header_map = _canonicalize_headers(df.columns)
        rename_map = {c: new for c, new in header_map.items() if new}
        df = df.rename(columns=rename_map)
        # сохраняем скидку из шапки отдельно
        df.attrs["discount_pct_header"] = disc_hdr
    else:
        df, _ = _csv_read(path, sep)
        df.columns = [_norm(c) for c in df.columns]
        header_map = _canonicalize_headers(df.columns)
        rename_map = {c: new for c, new in header_map.items() if new}
        df = df.rename(columns=rename_map)

    # обязательный столбец code
    if "code" not in df.columns:
        # попробуем найти по ключу
        candidate = None
        for c in df.columns:
            if _norm_key(c) in ("код", "code", "артикул"):
                candidate = c
                break
        if candidate:
            df = df.rename(columns={candidate: "code"})
        else:
            raise ValueError(
                "Не нашли колонку с кодом (Код / code / Артикул). Проверь шапку файла."
            )

    # зачистка значений
    for c in df.columns:
        df[c] = df[c].map(lambda x: _norm(x) if pd.notna(x) else None)

    return df


# =========================
# Upsert
# =========================
def upsert_records(df: pd.DataFrame, asof: date | datetime):
    # приведение типов
    if "price_rub" in df.columns:
        df["price_rub"] = df["price_rub"].map(_to_float)
    if "price_discount" in df.columns:
        df["price_discount"] = df["price_discount"].map(_to_float)

    for col in ("pack",):
        if col in df.columns:
            df[col] = df[col].map(_to_int)
    for col in ("volume", "abv"):
        if col in df.columns:
            df[col] = df[col].map(_to_float)

    for col in ("stock_total", "reserved", "stock_free"):
        if col in df.columns:
            df[col] = df[col].map(_to_int)

    disc: Optional[float] = df.attrs.get("discount_pct")

    ins_products = """
                   INSERT INTO products(code, producer, title_ru, country,
                                        region, grapes, abv, pack, volume,
                                        price_list_rub, price_final_rub,
                                        price_rub)
                   VALUES (%(code)s, %(producer)s, %(title_ru)s, %(country)s,
                           %(region)s, %(grapes)s, %(abv)s, %(pack)s,
                           %(volume)s, %(price_list_rub)s, %(price_final_rub)s,
                           %(price_rub)s)
                   ON CONFLICT (code) DO UPDATE SET
                       producer = EXCLUDED.producer,
                       title_ru = EXCLUDED.title_ru,
                       country = EXCLUDED.country,
                       region = EXCLUDED.region,
                       grapes = EXCLUDED.grapes,
                       abv = EXCLUDED.abv,
                       pack = EXCLUDED.pack,
                       volume = EXCLUDED.volume,
                       price_list_rub = EXCLUDED.price_list_rub,
                       price_final_rub = EXCLUDED.price_final_rub,
                       price_rub = EXCLUDED.price_rub;
                   """

    upsert_inventory = """
                       INSERT INTO inventory(code, stock_total, reserved,
                                             stock_free, asof_date)
                       VALUES (%s, %s, %s, %s, %s)
                       ON CONFLICT (code) DO UPDATE SET
                           stock_total = EXCLUDED.stock_total,
                           reserved = EXCLUDED.reserved,
                           stock_free = EXCLUDED.stock_free,
                           asof_date = EXCLUDED.asof_date;
                       """

    asof_dt = asof if isinstance(asof, datetime) else datetime.combine(asof, datetime.min.time())

    with get_conn() as conn, conn.cursor() as cur:
        total = 0
        prod_upd = 0
        inv_upd = 0
        price_hist = 0

        for _, r in df.iterrows():
            code = r.get("code")
            if not code:
                continue

            price_list = r.get("price_rub")
            price_file_disc = r.get("price_discount")

            price_calc_disc = None
            if disc is not None and price_list is not None:
                price_calc_disc = round(price_list * (1.0 - disc), 2)

            prefer_s5 = os.environ.get("PREFER_S5") in ("1", "true", "True")
            eff = price_calc_disc if prefer_s5 else price_file_disc
            if eff is None:
                eff = price_file_disc if prefer_s5 else price_calc_disc
            if eff is None:
                eff = price_list

            if (
                price_file_disc is not None
                and price_calc_disc is not None
                and abs(price_file_disc - price_calc_disc) > 0.01
            ):
                print(
                    f"[warn] {code}: price_discount mismatch -> file={price_file_disc} vs S5={price_calc_disc}"
                )

            payload = dict(
                code=code,
                producer=r.get("producer"),
                title_ru=r.get("title_ru"),
                country=r.get("country"),
                region=r.get("region"),
                grapes=r.get("grapes"),
                abv=r.get("abv"),
                pack=r.get("pack"),
                volume=r.get("volume"),
                price_list_rub=price_list,
                price_final_rub=eff,
                price_rub=eff,
            )
            cur.execute(ins_products, payload)
            prod_upd += 1

            if eff is not None:
                try:
                    eff_num = float(eff)
                    if math.isfinite(eff_num):
                        cur.execute("SELECT upsert_price(%s, %s, %s);", (code, eff_num, asof_dt))
                        price_hist += 1
                except Exception:
                    pass

            if any(r.get(k) is not None for k in ("stock_total", "reserved", "stock_free")):
                cur.execute(
                    upsert_inventory,
                    (
                        code,
                        r.get("stock_total"),
                        r.get("reserved"),
                        r.get("stock_free"),
                        asof_dt.date(),
                    ),
                )
                inv_upd += 1

            total += 1

        conn.commit()
        logger = logging.getLogger(__name__)
        logger.info(
            f"Upsert done: rows={total}, products_upd={prod_upd}, price_hist={price_hist}, inventory_upd={inv_upd}"
        )

    return total
