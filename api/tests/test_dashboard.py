# -*- coding: utf-8 -*-
from __future__ import annotations

from webapp import history, users_db
from webapp.tests.conftest import make_user


def _login(client, username, password):
    resp = client.post("/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp


def test_summary_requires_auth(isolated_state, client):
    resp = client.get("/dashboard/summary")
    assert resp.status_code == 401


def test_summary_reflects_history(isolated_state, client):
    make_user("reader1", "ReaderPass2026!", users_db.ROLE_READER)
    _login(client, "reader1", "ReaderPass2026!")

    history.record_run(action="extract_bc", source="admin", status="ok", ok=True, message="ok", log="")
    history.record_run(action="extract_bc", source="admin", status="error", ok=False, message="bad", log="")

    resp = client.get("/dashboard/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["running_count"] == 0
    assert body["active_schedule_count"] == 0
    assert body["recent_error_count"] == 1
    assert len(body["recent_history"]) == 2
