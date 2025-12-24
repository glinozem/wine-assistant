from __future__ import annotations

import argparse
import logging
import os
from dataclasses import dataclass
from typing import Tuple

import psycopg2
from psycopg2.extras import RealDictCursor

from scripts.db_connect import connect_postgres

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StaleConfig:
    running_minutes: int
    pending_minutes: int


def mark_stale_import_runs(conn: psycopg2.extensions.connection, cfg: StaleConfig) -> Tuple[int, int]:
    """
    Marks stale runs as rolled_back:
      - running with started_at older than running_minutes
      - pending with created_at older than pending_minutes
    Returns: (rolled_back_running, rolled_back_pending)
    """
    rolled_running = 0
    rolled_pending = 0

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            UPDATE import_runs
            SET status = 'rolled_back',
                error_summary = 'Stale run: timeout / crashed importer',
                finished_at = NOW()
            WHERE status = 'running'
              AND started_at IS NOT NULL
              AND started_at < NOW() - (%s || ' minutes')::interval
            RETURNING run_id
            """,
            (cfg.running_minutes,),
        )
        rolled_running = len(cur.fetchall())

        cur.execute(
            """
            UPDATE import_runs
            SET status = 'rolled_back',
                error_summary = 'Stale run: never started (stuck pending)',
                finished_at = NOW()
            WHERE status = 'pending'
              AND created_at < NOW() - (%s || ' minutes')::interval
            RETURNING run_id
            """,
            (cfg.pending_minutes,),
        )
        rolled_pending = len(cur.fetchall())

    return rolled_running, rolled_pending


def main() -> int:
    parser = argparse.ArgumentParser(description="Mark stale import_runs as rolled_back.")
    parser.add_argument("--running-minutes", type=int, default=int(os.getenv("STALE_RUNNING_MINUTES", "120")))
    parser.add_argument("--pending-minutes", type=int, default=int(os.getenv("STALE_PENDING_MINUTES", "15")))
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    cfg = StaleConfig(running_minutes=args.running_minutes, pending_minutes=args.pending_minutes)

    conn = connect_postgres()
    try:
        r1, r2 = mark_stale_import_runs(conn, cfg)
        conn.commit()
        logger.info("stale_import_runs_done rolled_back_running=%s rolled_back_pending=%s", r1, r2)
        return 0
    except Exception:
        conn.rollback()
        logger.exception("stale_import_runs_failed")
        return 2
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
