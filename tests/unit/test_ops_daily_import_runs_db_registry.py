import json
from datetime import datetime, timezone

import pytest
from flask import Flask, jsonify, request


@pytest.fixture()
def ops_client(tmp_path, monkeypatch):
    from api import ops_daily_import as mod

    # isolate FS
    logs = tmp_path / "logs"
    logs.mkdir()
    monkeypatch.setattr(mod, "LOGS_DIR", logs)

    app = Flask(__name__)

    # minimal API-key gate
    def require_api_key(fn):
        def wrapper(*a, **kw):
            if request.headers.get("X-API-Key") != "testkey":
                return jsonify({"error": "forbidden"}), 403
            return fn(*a, **kw)
        wrapper.__name__ = fn.__name__
        return wrapper

    class DummyConn:
        def close(self): pass

    state = {"db_mode": "ok", "calls": 0}

    def db_connect():
        if state["db_mode"] == "down":
            return None, "db down"
        return DummyConn(), None

    def db_query(conn, sql, params=()):
        if "FROM public.ops_daily_import_runs" in sql and "WHERE run_id" not in sql:
            # list: return limit+1 rows
            return [
                {"run_id": "11111111-1111-1111-1111-111111111111",
                 "status": "OK",
                 "requested_mode": "auto",
                 "selected_mode": "AUTO_LATEST",
                 "started_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
                 "finished_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
                 "duration_ms": 1000,
                 "summary": {"files_total": 1, "files_imported": 1,
                             "files_skipped": 0, "files_quarantined": 0,
                             "files_failed": 0}},
                {"run_id": "22222222-2222-2222-2222-222222222222",
                 "status": "OK",
                 "requested_mode": "auto",
                 "selected_mode": "AUTO_LATEST",
                 "started_at": datetime(2025, 12, 31, tzinfo=timezone.utc),
                 "finished_at": datetime(2025, 12, 31, tzinfo=timezone.utc),
                 "duration_ms": 900,
                 "summary": {"files_total": 1, "files_imported": 1,
                             "files_skipped": 0, "files_quarantined": 0,
                             "files_failed": 0}},
                # extra row => next_cursor should exist for limit=2
                {"run_id": "33333333-3333-3333-3333-333333333333",
                 "status": "FAILED",
                 "requested_mode": "files",
                 "selected_mode": "MANUAL_LIST",
                 "started_at": datetime(2025, 12, 30, tzinfo=timezone.utc),
                 "finished_at": datetime(2025, 12, 30, tzinfo=timezone.utc),
                 "duration_ms": 800,
                 "summary": {"files_total": 1, "files_imported": 0,
                             "files_skipped": 0, "files_quarantined": 0,
                             "files_failed": 1}},
            ]

        if "FROM public.ops_daily_import_runs" in sql and "WHERE run_id" in sql:
            return [{
                "run_id": "33333333-3333-3333-3333-333333333333",
                "status": "FAILED",
                "result_json": {
                    "run_id": "33333333-3333-3333-3333-333333333333",
                    "status": "FAILED"},
            }]

        return []

    mod.register_ops_daily_import(app, require_api_key, db_connect, db_query)
    return app.test_client(), state, logs

def test_runs_list_db_contract_and_next_cursor(ops_client):
    client, state, _ = ops_client
    r = client.get("/api/v1/ops/daily-import/runs?limit=2", headers={"X-API-Key":"testkey"})
    assert r.status_code == 200
    data = r.get_json()

    # New stable contract
    assert "items" in data
    assert len(data["items"]) == 2
    assert data.get("next_cursor")  # because we returned limit+1

    # Backward compat alias
    assert "runs" in data
    assert len(data["runs"]) == 2

def test_run_detail_db_first(ops_client):
    client, state, _ = ops_client
    # first call warms state["calls"] for the stub; second call returns run_log
    client.get("/api/v1/ops/daily-import/runs?limit=2", headers={"X-API-Key":"testkey"})
    r = client.get("/api/v1/ops/daily-import/runs/33333333-3333-3333-3333-333333333333",
                   headers={"X-API-Key":"testkey"})
    assert r.status_code == 200
    data = r.get_json()
    assert data["run_id"].startswith("33333333")
    assert data["status"] == "FAILED"

def test_runs_list_fs_fallback_when_db_down(ops_client):
    client, state, logs = ops_client
    state["db_mode"] = "down"

    # prepare FS log
    (logs / "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa.json").write_text(json.dumps({
        "run_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "status": "OK",
        "started_at": "2026-01-01T00:00:00+00:00",
        "finished_at": "2026-01-01T00:00:01+00:00",
        "duration_ms": 1000,
        "summary": {"files_total": 1, "files_imported": 1, "files_skipped": 0, "files_quarantined": 0, "files_failed": 0}
    }), encoding="utf-8")

    r = client.get("/api/v1/ops/daily-import/runs?limit=50", headers={"X-API-Key":"testkey"})
    assert r.status_code == 200
    data = r.get_json()
    assert data["runs"][0]["run_id"].startswith("aaaaaaaa")
