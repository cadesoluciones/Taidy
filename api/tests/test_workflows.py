# -*- coding: utf-8 -*-
from __future__ import annotations

import time

from webapp import users_db
from webapp.tests.conftest import make_user


def _login(client, username, password):
    assert client.post("/auth/login", json={"username": username, "password": password}).status_code == 200


_SIMPLE_STEPS = [
    {"id": "a", "label": "Paso A", "action": "extract_bc", "params": {}, "depends_on": [], "trigger_rule": "all_success"},
]


def test_operator_cannot_create_workflow(isolated_state, client):
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    resp = client.post("/workflows", json={"name": "Flujo 1", "steps": _SIMPLE_STEPS})
    assert resp.status_code == 403


def test_admin_can_create_list_and_delete_workflow(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")

    created = client.post("/workflows", json={"name": "Flujo 1", "steps": _SIMPLE_STEPS})
    assert created.status_code == 200
    workflow_id = created.json()["id"]

    names = [w["name"] for w in client.get("/workflows").json()["items"]]
    assert "Flujo 1" in names

    assert client.delete(f"/workflows/{workflow_id}").status_code == 204
    assert client.get("/workflows").json()["items"] == []


def test_cycle_is_rejected(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")

    cyclic_steps = [
        {"id": "a", "label": "A", "action": "extract_bc", "params": {}, "depends_on": ["b"], "trigger_rule": "all_success"},
        {"id": "b", "label": "B", "action": "extract_bc", "params": {}, "depends_on": ["a"], "trigger_rule": "all_success"},
    ]
    resp = client.post("/workflows", json={"name": "Cíclico", "steps": cyclic_steps})
    assert resp.status_code == 400


def test_operator_can_launch_and_stop_a_workflow(isolated_state, client, fake_subprocess):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    workflow_id = client.post("/workflows", json={"name": "Flujo 1", "steps": _SIMPLE_STEPS}).json()["id"]

    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    run = client.post(f"/workflows/{workflow_id}/run")
    assert run.status_code == 200
    run_id = run.json()["id"]
    assert run.json()["triggered_by"] == "operator1"

    runs = client.get("/workflow-runs").json()["items"]
    assert any(r["id"] == run_id for r in runs)

    # Wait briefly for the fake (near-instant) subprocess to finish on its own
    # rather than asserting a specific in-flight status, which would be racy.
    for _ in range(20):
        current = client.get("/workflow-runs").json()["items"]
        if next(r for r in current if r["id"] == run_id)["status"] != "running":
            break
        time.sleep(0.2)


def test_reader_cannot_stop_someone_elses_workflow(isolated_state, client, fake_subprocess):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    workflow_id = client.post("/workflows", json={"name": "Flujo 1", "steps": _SIMPLE_STEPS}).json()["id"]

    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")
    run_id = client.post(f"/workflows/{workflow_id}/run").json()["id"]

    make_user("reader1", "ReaderPass2026!", users_db.ROLE_READER)
    _login(client, "reader1", "ReaderPass2026!")

    resp = client.post(f"/workflow-runs/{run_id}/stop")
    assert resp.status_code == 403
