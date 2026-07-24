# -*- coding: utf-8 -*-
from __future__ import annotations

from webapp import history, users_db
from webapp.tests.conftest import make_user


def _login(client, username, password):
    assert client.post("/auth/login", json={"username": username, "password": password}).status_code == 200


def test_history_filters_by_result(isolated_state, client):
    make_user("reader1", "ReaderPass2026!", users_db.ROLE_READER)
    _login(client, "reader1", "ReaderPass2026!")

    history.record_run(action="extract_bc", source="admin", status="ok", ok=True, message="ok", log="")
    history.record_run(action="sync_factorial", source="admin", status="error", ok=False, message="bad", log="tb")

    resp = client.get("/history")
    assert resp.status_code == 200
    assert resp.json()["total_matching"] == 2

    resp = client.get("/history", params={"result": "error"})
    body = resp.json()
    assert body["total_matching"] == 1
    assert body["items"][0]["action"] == "sync_factorial"


def test_history_pagination(isolated_state, client):
    make_user("reader1", "ReaderPass2026!", users_db.ROLE_READER)
    _login(client, "reader1", "ReaderPass2026!")

    for i in range(25):
        history.record_run(action="extract_bc", source="admin", status="ok", ok=True, message=f"run {i}", log="")

    resp = client.get("/history", params={"page_size": 20, "page": 1})
    body = resp.json()
    assert body["total_matching"] == 25
    assert body["total_pages"] == 2
    assert len(body["items"]) == 20

    resp2 = client.get("/history", params={"page_size": 20, "page": 2})
    assert len(resp2.json()["items"]) == 5
