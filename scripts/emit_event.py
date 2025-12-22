"""Emit structured JSON log events.

Primary use cases:
- Produce machine-parsable JSONL events for backup/DR workflows.
- Append events to a local log file that can be scraped by Promtail/Loki.

This module intentionally has no third-party dependencies.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_value(raw: str) -> Any:
    s = raw.strip()
    if s.lower() in {"true", "false"}:
        return s.lower() == "true"
    if s.lower() in {"null", "none"}:
        return None
    # Try int, then float
    try:
        if s.startswith("0") and len(s) > 1 and s[1].isdigit():
            # Avoid surprising octal-ish coercion; keep as string for leading-zero values.
            raise ValueError
        return int(s)
    except Exception:
        pass
    try:
        return float(s)
    except Exception:
        return s


def _parse_kv(pair: str) -> Tuple[str, Any]:
    if "=" not in pair:
        raise argparse.ArgumentTypeError(f"Expected key=value, got: {pair!r}")
    k, v = pair.split("=", 1)
    k = k.strip()
    if not k:
        raise argparse.ArgumentTypeError(f"Empty key in: {pair!r}")
    return k, _coerce_value(v)


def _stat_file(path: Path) -> Dict[str, Any]:
    st = path.stat()
    return {
        "stat_path": str(path),
        "size_bytes": st.st_size,
        "mtime_unix": int(st.st_mtime),
    }


@dataclass(frozen=True)
class Event:
    level: str
    service: str
    event: str
    fields: Dict[str, Any]

    def to_json(self) -> Dict[str, Any]:
        now = _utc_now()
        base: Dict[str, Any] = {
            "ts": now.isoformat().replace("+00:00", "Z"),
            "ts_unix": int(now.timestamp()),
            "level": self.level,
            "service": self.service,
            "event": self.event,
        }
        base.update(self.fields)
        return base


def emit(event: Event, *, log_file: Optional[Path] = None) -> str:
    line = json.dumps(event.to_json(), ensure_ascii=False)
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    print(line)
    return line


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="scripts.emit_event")
    p.add_argument("--event", required=True, help="Event name, e.g. backup_local_started")
    p.add_argument("--service", default="backup", help="Service name, e.g. backup / dr_smoke")
    p.add_argument("--level", default="info", help="Log level, e.g. info / warning / error")
    p.add_argument("--log-file", default=None, help="Append event as JSONL to this file (recommended for Promtail)")
    p.add_argument("--stat-file", default=None, help="If set, include file stats (size_bytes, mtime_unix)")
    p.add_argument(
        "--field",
        action="append",
        default=[],
        help="Extra fields as key=value (repeatable). Basic types are auto-detected.",
    )

    args = p.parse_args(argv)

    fields: Dict[str, Any] = {}
    for pair in args.field:
        k, v = _parse_kv(pair)
        fields[k] = v

    if args.stat_file:
        fp = Path(args.stat_file)
        if not fp.exists():
            # Keep behavior explicit and debuggable; do not silently skip.
            raise SystemExit(f"stat-file does not exist: {fp}")
        fields.update(_stat_file(fp))

    log_file = Path(args.log_file) if args.log_file else None
    emit(Event(level=args.level, service=args.service, event=args.event, fields=fields), log_file=log_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
