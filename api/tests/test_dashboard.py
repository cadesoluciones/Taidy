# -*- coding: utf-8 -*-
from __future__ import annotations

import time

from webapp import history, users_db
from webapp.tests.conftest import make_user

_SIMPLE_STEPS = [{"id": "a", "label": "Paso A", "action": "extract_bc", "params": {}, "depends_on": [], "trigger_rule": "all_success"}]


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


# --------------------------------------------------------------------------------------
# GET /dashboard/mine-workflows -- backs Reader's simplified Inicio.
# --------------------------------------------------------------------------------------


def test_mine_workflows_empty_for_reader_with_no_access(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    client.post("/workflows", json={"name": "Flujo ajeno", "steps": _SIMPLE_STEPS})

    make_user("reader1", "ReaderPass2026!", users_db.ROLE_READER)
    _login(client, "reader1", "ReaderPass2026!")

    resp = client.get("/dashboard/mine-workflows")
    assert resp.status_code == 200
    assert resp.json()["items"] == []


def test_mine_workflows_shows_assigned_workflow_with_no_activity(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    workflow_id = client.post("/workflows", json={"name": "Flujo RRHH", "steps": _SIMPLE_STEPS}).json()["id"]
    client.patch(f"/workflows/{workflow_id}/reader-access", json={"reader_usernames": ["reader1"]})

    make_user("reader1", "ReaderPass2026!", users_db.ROLE_READER)
    _login(client, "reader1", "ReaderPass2026!")

    resp = client.get("/dashboard/mine-workflows")
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == workflow_id
    assert items[0]["current_run"] is None
    assert items[0]["last_run"] is None
    assert items[0]["scheduled"] is False


def test_mine_workflows_scheduled_flag_reflects_a_matching_enabled_schedule(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    workflow_id = client.post("/workflows", json={"name": "Flujo RRHH", "steps": _SIMPLE_STEPS}).json()["id"]
    client.patch(f"/workflows/{workflow_id}/reader-access", json={"reader_usernames": ["reader1"]})
    client.post(
        "/schedules",
        json={
            "name": "RRHH nocturno",
            "action": "run_workflow",
            "params": {"workflow_id": workflow_id},
            "trigger": "interval",
            "trigger_args": {"hours": 24},
        },
    )

    make_user("reader1", "ReaderPass2026!", users_db.ROLE_READER)
    _login(client, "reader1", "ReaderPass2026!")

    items = client.get("/dashboard/mine-workflows").json()["items"]
    assert items[0]["scheduled"] is True


def test_mine_workflows_shows_last_run_once_it_finishes(isolated_state, client, fake_subprocess):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    workflow_id = client.post("/workflows", json={"name": "Flujo RRHH", "steps": _SIMPLE_STEPS}).json()["id"]
    client.patch(f"/workflows/{workflow_id}/reader-access", json={"reader_usernames": ["reader1"]})

    make_user("reader1", "ReaderPass2026!", users_db.ROLE_READER)
    _login(client, "reader1", "ReaderPass2026!")
    run_id = client.post(f"/workflows/{workflow_id}/run").json()["id"]

    for _ in range(40):
        items = client.get("/dashboard/mine-workflows").json()["items"]
        if items[0]["current_run"] is None and items[0]["last_run"] is not None:
            break
        time.sleep(0.3)

    assert items[0]["last_run"] is not None, "workflow run never settled within the poll window"
    assert items[0]["last_run"]["id"] == run_id


def test_mine_workflows_operator_and_admin_see_every_workflow_unfiltered(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    client.post("/workflows", json={"name": "Flujo 1", "steps": _SIMPLE_STEPS})
    client.post("/workflows", json={"name": "Flujo 2", "steps": _SIMPLE_STEPS})

    admin_items = client.get("/dashboard/mine-workflows").json()["items"]
    assert len(admin_items) == 2

    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")
    operator_items = client.get("/dashboard/mine-workflows").json()["items"]
    assert len(operator_items) == 2
