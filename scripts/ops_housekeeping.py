from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

IGNORE_NAMES = {".gitkeep"}


@dataclass(frozen=True)
class Candidate:
    path: Path
    mtime: datetime
    size_bytes: int


def select_candidates(base_dir: Path, *, older_than_days: int, now: datetime) -> list[Candidate]:
    """
    Возвращает файлы старше older_than_days, рекурсивно.
    Ничего не удаляет. Только план.

    Правила:
      - older_than_days <= 0 => пустой список
      - учитываем только файлы (не директории)
      - пропускаем IGNORE_NAMES
      - mtime сравниваем в UTC
      - результат сортируем стабильно по path (posix)
    """
    if older_than_days <= 0:
        return []

    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    if not base_dir.exists():
        return []

    cutoff = now - timedelta(days=older_than_days)
    out: list[Candidate] = []

    for p in base_dir.rglob("*"):
        if not p.is_file():
            continue
        if p.name in IGNORE_NAMES:
            continue

        st = p.stat()
        mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
        if mtime < cutoff:
            out.append(Candidate(path=p, mtime=mtime, size_bytes=st.st_size))

    out.sort(key=lambda c: c.path.as_posix())
    return out


def _fmt_bytes(n: int) -> str:
    # простой человекочитаемый формат, без внешних зависимостей
    units = ["B", "KB", "MB", "GB", "TB"]
    v = float(n)
    for u in units:
        if v < 1024.0 or u == units[-1]:
            if u == "B":
                return f"{int(v)} {u}"
            return f"{v:.1f} {u}"
        v /= 1024.0
    return f"{n} B"


def _zone_plan(
    zone_name: str,
    base_dir: Path,
    *,
    older_than_days: int,
    now: datetime,
) -> tuple[str, list[Candidate]]:
    candidates = select_candidates(base_dir, older_than_days=older_than_days, now=now)
    return zone_name, candidates


def _min_age_guard(
    plans: list[tuple[str, list[Candidate]]],
    *,
    now: datetime,
    min_age_days: int,
) -> list[Candidate]:
    """Возвращает список файлов, которые моложе min_age_days (т.е. потенциально опасно удалять)."""
    if min_age_days <= 0:
        return []

    cutoff = now - timedelta(days=min_age_days)
    too_young: list[Candidate] = []
    for _zone, items in plans:
        for c in items:
            # c.mtime в UTC; cutoff — tz-aware
            if c.mtime >= cutoff:
                too_young.append(c)
    too_young.sort(key=lambda c: c.path.as_posix())
    return too_young


def _apply_delete(plans: list[tuple[str, list[Candidate]]]) -> int:
    deleted = 0
    for _zone, items in plans:
        for c in items:
            try:
                c.path.unlink(missing_ok=True)
                deleted += 1
            except FileNotFoundError:
                # race ok
                continue
    return deleted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ops_housekeeping",
        description="Retention / housekeeping for Daily Import directories (dry-run by default).",
    )
    parser.add_argument("--days-inbox", type=int, default=0)
    parser.add_argument("--days-archive", type=int, default=0)
    parser.add_argument("--days-quarantine", type=int, default=0)
    parser.add_argument("--days-logs", type=int, default=0)

    parser.add_argument("--apply", action="store_true", help="Actually delete files. Default: dry-run.")
    parser.add_argument("--force", action="store_true", help="Bypass safety guards.")
    parser.add_argument("--min-age-days", type=int, default=7, help="Safety: do not delete files newer than this without --force.")
    parser.add_argument("--limit", type=int, default=20, help="Limit printed paths per zone.")

    args = parser.parse_args(argv)

    now = datetime.now(timezone.utc)

    zones: list[tuple[str, Path, int]] = [
        ("inbox", Path("data/inbox"), args.days_inbox),
        ("archive", Path("data/archive"), args.days_archive),
        ("quarantine", Path("data/quarantine"), args.days_quarantine),
        ("logs", Path("data/logs/daily-import"), args.days_logs),
    ]

    plans: list[tuple[str, list[Candidate]]] = []
    for name, base_dir, days in zones:
        if days <= 0:
            continue
        plans.append(_zone_plan(name, base_dir, older_than_days=days, now=now))

    total_files = sum(len(items) for _z, items in plans)
    total_bytes = sum(c.size_bytes for _z, items in plans for c in items)

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"housekeeping mode={mode} now_utc={now.isoformat()} zones={len(plans)}")
    print(f"total candidates: {total_files} files, {_fmt_bytes(total_bytes)}")

    for zone, items in plans:
        z_bytes = sum(c.size_bytes for c in items)
        print(f"\n[{zone}] candidates: {len(items)} files, {_fmt_bytes(z_bytes)}")
        for c in items[: max(args.limit, 0)]:
            print(f"  {c.path.as_posix()}  mtime={c.mtime.isoformat()}  size={c.size_bytes}")

        if args.limit >= 0 and len(items) > args.limit:
            print(f"  ... ({len(items) - args.limit} more)")

    if args.apply:
        too_young = _min_age_guard(plans, now=now, min_age_days=args.min_age_days)
        if too_young and not args.force:
            print(
                f"\nERROR: safety guard triggered: {len(too_young)} candidate files are newer than min_age_days={args.min_age_days}.",
                file=sys.stderr,
            )
            print("Refusing to delete. Re-run with --force to bypass.", file=sys.stderr)
            return 2

        deleted = _apply_delete(plans)
        print(f"\nDELETED: {deleted} files")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
