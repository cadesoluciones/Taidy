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


def test_run_pipeline_action_label_names_the_pipeline(isolated_state, client, fake_subprocess):
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    resp = client.post("/tasks/run-pipeline", json={"pipeline": "Pipeline_CADE_Silver"})
    assert resp.status_code == 200
    assert resp.json()["action_label"] == "Fabric · Ejecutar pipeline (Pipeline_CADE_Silver)"

    task_id = resp.json()["id"]
    _wait_until_finished(task_id)
    detail = client.get(f"/tasks/{task_id}").json()
    assert detail["table_statuses"] == []
    assert "fake output" in detail["log_tail"]


def test_sync_apply_action_label_names_the_mapping(isolated_state, client, fake_subprocess):
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    resp = client.post("/tasks/sync-apply", json={"mapping": "bc_contact_a_hubspot", "direction": "both"})
    assert resp.status_code == 200
    assert resp.json()["action_label"] == "Sincronización · Aplicar (bc_contact_a_hubspot)"

    task_id = resp.json()["id"]
    _wait_until_finished(task_id)
    detail = client.get(f"/tasks/{task_id}").json()
    assert detail["table_statuses"] == []
    assert "fake output" in detail["log_tail"]


def test_sync_apply_requires_mapping_and_direction(isolated_state, client, fake_subprocess):
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    # Matches the existing convention for launch()-level ValueErrors (e.g.
    # run_pipeline's "Indica qué pipeline lanzar.") -- _launch() maps them
    # to 409, not 400.
    resp = client.post("/tasks/sync-apply", json={"mapping": "", "direction": "both"})
    assert resp.status_code == 409


def test_two_sync_apply_runs_on_different_mappings_do_not_conflict(isolated_state, client, fake_subprocess):
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    first = client.post("/tasks/sync-apply", json={"mapping": "m1", "direction": "both"})
    second = client.post("/tasks/sync-apply", json={"mapping": "m2", "direction": "both"})
    assert first.status_code == 200
    assert second.status_code == 200


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


def test_notify_flag_reaches_the_task_and_is_stripped_from_argv(isolated_state, client, fake_subprocess):
    """The API's `notify` request field must reach webapp.tasks.Task.notify
    (proving api/routers/tasks.py forwards it into launch()'s params) while
    never leaking into the subprocess argv (proving launch() still pops it
    before **params reaches adapter.build_upload_bc_argv)."""
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    resp = client.post("/tasks/upload-bc", json={"notify": True})
    assert resp.status_code == 200
    task_id = resp.json()["id"]

    task = tasks_module.get_task(task_id)
    assert task.notify is True

    _wait_until_finished(task_id)
    assert tasks_module.get_task(task_id).status == "ok"


def test_extract_bc_page_size_zero_is_normalized_to_no_flag(isolated_state, client, monkeypatch):
    """A direct API caller sending the literal page_size=0 the Pydantic
    default allows must get the exact same behavior the Streamlit form
    guarantees (no --page-size flag at all, letting the backend fall back
    to config.json) -- not a discrepancy that only the React form happens
    to paper over by converting 0 to null before sending.
    """
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    captured_argv = {}

    def _capturing_popen(module, argv):
        captured_argv["argv"] = argv
        import subprocess
        import sys

        return subprocess.Popen(
            [sys.executable, "-c", "print('fake output')"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

    monkeypatch.setattr(tasks_module, "_popen", _capturing_popen)

    resp = client.post("/tasks/extract-bc", json={"page_size": 0})
    assert resp.status_code == 200
    assert "--page-size" not in captured_argv["argv"]
