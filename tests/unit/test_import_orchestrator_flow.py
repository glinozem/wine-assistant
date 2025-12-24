from datetime import date

import pytest

from scripts.import_orchestrator import run_import_orchestrator

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def _clean_import_runs(db_connection):
    # ВАЖНО: тесты делают COMMIT, поэтому чистим явно
    with db_connection.cursor() as cur:
        cur.execute("TRUNCATE TABLE import_runs CASCADE")
    db_connection.commit()


def _dummy_import_success(conn, *, supplier, file_path, as_of_date, run_id, envelope_id, **kwargs):
    with conn.cursor() as cur:
        cur.execute("SELECT 1")
    return {"metrics": {"total_rows_processed": 10, "new_sku_count": 2}, "artifacts": {"log": "n/a"}}


def _dummy_import_fail(conn, *, supplier, file_path, as_of_date, run_id, envelope_id, **kwargs):
    raise RuntimeError("Dummy import failure")


def test_orchestrator_success_then_skip(db_connection, tmp_path):
    f = tmp_path / "supplier1_20251223.xlsx"
    f.write_text("data")

    r1 = run_import_orchestrator(
        db_connection,
        supplier="supplier1",
        file_path=str(f),
        as_of_date=date(2025, 12, 23),
        triggered_by="test",
        import_fn=_dummy_import_success,
        create_skipped_audit_row=False,
    )
    assert r1.status == "success"
    assert r1.run_id is not None

    r2 = run_import_orchestrator(
        db_connection,
        supplier="supplier1",
        file_path=str(f),
        as_of_date=date(2025, 12, 23),
        triggered_by="test2",
        import_fn=_dummy_import_success,
        create_skipped_audit_row=True,
    )
    assert r2.status == "skipped"


def test_orchestrator_failed_allows_retry(db_connection, tmp_path):
    f = tmp_path / "supplier1_20251223.xlsx"
    f.write_text("data")

    r1 = run_import_orchestrator(
        db_connection,
        supplier="supplier1",
        file_path=str(f),
        as_of_date=date(2025, 12, 23),
        triggered_by="test",
        import_fn=_dummy_import_fail,
        create_skipped_audit_row=False,
    )
    assert r1.status == "failed"

    r2 = run_import_orchestrator(
        db_connection,
        supplier="supplier1",
        file_path=str(f),
        as_of_date=date(2025, 12, 23),
        triggered_by="retry",
        import_fn=_dummy_import_success,
        create_skipped_audit_row=False,
    )
    assert r2.status == "success"
    assert r2.run_id is not None
    assert r2.run_id != r1.run_id
