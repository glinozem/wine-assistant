import pathlib
import re
import sys

PATS = [
    r"AKIA[0-9A-Z]{16}",
    r"ASIA[0-9A-Z]{16}",
    r"AIza[0-9A-Za-z\-_]{35}",
    r"-----BEGIN (RSA|EC) PRIVATE KEY-----",
    r"AzureStorageKey|SharedAccessKey|AccountKey=",
]
bad = False
for p in map(pathlib.Path, sys.argv[1:]):
    if p.is_file():
        try:
            s = p.read_text(errors="ignore")
        except Exception:
            continue
        if any(re.search(pat, s) for pat in PATS):
            print(f"[BLOCK] possible secret in {p}")
            bad = True
sys.exit(1 if bad else 0)
