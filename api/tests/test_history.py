# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import io

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


def test_history_entry_carries_the_per_record_details_when_present(isolated_state, client):
    make_user("reader1", "ReaderPass2026!", users_db.ROLE_READER)
    _login(client, "reader1", "ReaderPass2026!")

    history.record_run(action="extract_bc", source="admin", status="ok", ok=True, message="sin desglose", log="")
    history.record_run(
        action="sync_apply",
        source="admin",
        status="ok",
        ok=True,
        message="con desglose",
        log="",
        details=[{"key": "a@x.com", "kind": "create_target", "outcome": "created", "detail": ""}],
    )

    items = {i["message"]: i for i in client.get("/history").json()["items"]}
    assert items["sin desglose"]["details"] is None
    assert items["con desglose"]["details"] == [
        {"key": "a@x.com", "kind": "create_target", "outcome": "created", "detail": ""}
    ]


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


def test_export_csv_contains_the_full_filtered_set_not_just_one_page(isolated_state, client):
    make_user("reader1", "ReaderPass2026!", users_db.ROLE_READER)
    _login(client, "reader1", "ReaderPass2026!")

    for i in range(25):
        history.record_run(action="extract_bc", source="admin", status="ok", ok=True, message=f"run {i}", log="")
    history.record_run(action="sync_factorial", source="admin", status="error", ok=False, message="bad", log="tb")

    resp = client.get("/history/export.csv")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert 'filename="historial.csv"' in resp.headers["content-disposition"]

    rows = list(csv.DictReader(io.StringIO(resp.text)))
    assert len(rows) == 26  # every matching entry, unpaginated


def test_export_csv_respects_filters_and_labels_the_result_in_spanish(isolated_state, client):
    make_user("reader1", "ReaderPass2026!", users_db.ROLE_READER)
    _login(client, "reader1", "ReaderPass2026!")

    history.record_run(action="extract_bc", source="admin", status="ok", ok=True, message="ok", log="")
    history.record_run(action="sync_factorial", source="admin", status="error", ok=False, message="bad", log="tb")

    resp = client.get("/history/export.csv", params={"result": "error"})
    rows = list(csv.DictReader(io.StringIO(resp.text)))
    assert len(rows) == 1
    assert rows[0]["Acción"] == "sync_factorial"
    assert rows[0]["Resultado"] == "Error"
