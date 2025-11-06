import math
import re



def parse_abv(value):
    if value is None:
        return None
    s = str(value).strip().replace(",", ".")
    m = re.search(r"(\d+(?:\.\d+)?)\s*%?", s)
    return f"{m.group(1)}%" if m else None


def normalize_volume(value):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    s = str(value).strip().lower().replace(",", ".")
    if "0.75" in s or "750" in s:
        return "0.75L"
    if "0.5" in s or "500" in s:
        return "0.5L"
    if "1.5" in s or "1500" in s:
        return "1.5L"
    if "24" in s:
        return "24L"
    if "1l" in s or s == "1":
        return "1L"
    return None


def to_number(value):
    if value is None:
        return None
    s = str(value).replace(" ", "").replace("\xa0", "").replace(",", ".")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group(0)) if m else None


def norm_str(x):
    return str(x).strip() if x is not None else None
