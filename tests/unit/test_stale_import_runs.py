from datetime import date

import pytest

from scripts.import_run_registry import ImportRunRegistry
from scripts.mark_stale_import_runs import StaleConfig, mark_stale_import_runs

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def _clean_import_runs(db_connection):
    with db_connection.cursor() as cur:
        cur.execute("TRUNCATE TABLE import_runs CASCADE")
    db_connection.commit()


def test_stale_detector_marks_running_as_rolled_back(db_connection, tmp_path):
    f = tmp_path / "supplier1_20251223.xlsx"
    f.write_text("data")

    reg = ImportRunRegistry(db_connection)
    run_id = reg.create_attempt(
        supplier="supplier1",
        file_path=str(f),
        as_of_date=date(2025, 12, 23),
        triggered_by="test",
    )
    db_connection.commit()
    reg.mark_running(run_id)
    db_connection.commit()

    # make it stale
    with db_connection.cursor() as cur:
        cur.execute("UPDATE import_runs SET started_at = NOW() - INTERVAL '3 hours' WHERE run_id = %s", (run_id,))
    db_connection.commit()

    r1, r2 = mark_stale_import_runs(db_connection, StaleConfig(running_minutes=120, pending_minutes=15))
    db_connection.commit()

    assert r1 == 1
    assert r2 == 0

    with db_connection.cursor() as cur:
        cur.execute("SELECT status FROM import_runs WHERE run_id = %s", (run_id,))
        status = cur.fetchone()[0]
    assert status == "rolled_back"
