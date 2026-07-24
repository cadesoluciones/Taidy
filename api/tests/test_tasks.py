# -*- coding: utf-8 -*-
from __future__ import annotations

import time

from webapp import tasks as tasks_module, users_db
from webapp.tests.conftest import make_user


def _login(client, username, password):
    assert client.post("/auth/login", json={"username": username, "password": password}).status_code == 200


def _wait_until_finished(task_id: str, timeout: float = 10.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        task = tasks_module.get_task(task_id)
        if task is not None and task.status in ("ok", "error", "stopped"):
            return
        time.sleep(0.05)


def test_reader_cannot_launch_a_task(isolated_state, client, fake_subprocess):
    make_user("reader1", "ReaderPass2026!", users_db.ROLE_READER)
    _login(client, "reader1", "ReaderPass2026!")

    resp = client.post("/tasks/sync-bc", json={})
    assert resp.status_code == 403
    assert client.get("/tasks").json()["items"] == []


def test_operator_can_launch_sync_bc_and_it_completes(isolated_state, client, fake_subprocess):
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    resp = client.post("/tasks/sync-bc", json={})
    assert resp.status_code == 200
    task_id = resp.json()["id"]
    assert resp.json()["action"] == "sync_bc"
    assert resp.json()["triggered_by"] == "operator1"

    _wait_until_finished(task_id)
    detail = client.get(f"/tasks/{task_id}").json()
    assert detail["status"] == "ok"


def test_reset_watermarks_requires_admin(isolated_state, client, fake_subprocess):
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    resp = client.post("/tasks/extract-bc", json={"reset_watermarks": True})
    assert resp.status_code == 403
    assert client.get("/tasks").json()["items"] == []


def test_factorial_date_validation(isolated_state, client, fake_subprocess):
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    resp = client.post(
        "/tasks/extract-factorial",
        json={"start_on": "2026-02-01", "end_on": "2026-01-01"},
    )
    assert resp.status_code == 400


def test_task_list_filters_by_action(isolated_state, client, fake_subprocess):
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    bc_task = client.post("/tasks/sync-bc", json={}).json()
    _wait_until_finished(bc_task["id"])
    fac_task = client.post(
        "/tasks/extract-factorial", json={"start_on": "2026-01-01", "end_on": "2026-01-31"}
    ).json()
    _wait_until_finished(fac_task["id"])

    resp = client.get("/tasks", params={"action": "sync_bc"})
    actions = [t["action"] for t in resp.json()["items"]]
    assert actions == ["sync_bc"]


def test_stop_requires_ownership_or_admin(isolated_state, client, fake_subprocess):
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")
    task_id = client.post("/tasks/sync-bc", json={}).json()["id"]

    make_user("operator2", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator2", "OperatorPass2026!")

    resp = client.post(f"/tasks/{task_id}/stop")
    assert resp.status_code == 403
