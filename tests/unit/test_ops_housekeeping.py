from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from scripts.ops_housekeeping import IGNORE_NAMES, select_candidates


def _set_mtime(path: Path, *, dt_utc: datetime) -> None:
    # os.utime expects POSIX timestamp (float seconds)
    ts = dt_utc.timestamp()
    os.utime(path, (ts, ts))


def test_select_candidates_filters_by_age(tmp_path: Path) -> None:
    base = tmp_path / "archive"
    base.mkdir()

    now = datetime(2026, 2, 8, 0, 0, 0, tzinfo=timezone.utc)

    old_file = base / "old.txt"
    new_file = base / "new.txt"
    old_file.write_text("old", encoding="utf-8")
    new_file.write_text("new", encoding="utf-8")

    # older_than_days=10 => cutoff = now - 10 days
    # make old_file 20 days old, new_file 2 days old
    _set_mtime(old_file, dt_utc=datetime(2026, 1, 19, 0, 0, 0, tzinfo=timezone.utc))
    _set_mtime(new_file, dt_utc=datetime(2026, 2, 6, 0, 0, 0, tzinfo=timezone.utc))

    got = select_candidates(base, older_than_days=10, now=now)
    got_paths = [c.path.name for c in got]

    assert got_paths == ["old.txt"]


def test_select_candidates_ignores_gitkeep(tmp_path: Path) -> None:
    base = tmp_path / "inbox"
    base.mkdir()

    now = datetime(2026, 2, 8, 0, 0, 0, tzinfo=timezone.utc)

    gitkeep_name = next(iter(IGNORE_NAMES))
    gitkeep = base / gitkeep_name
    gitkeep.write_text("", encoding="utf-8")
    _set_mtime(gitkeep, dt_utc=datetime(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc))

    got = select_candidates(base, older_than_days=1, now=now)
    assert got == []
