# -*- coding: utf-8 -*-
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from webapp import tasks, users_db, workflow_engine
from webapp.tests.conftest import make_user

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

_RETRY_STEPS = [
    {"id": "a", "label": "Paso A", "action": "extract_bc", "params": {}, "depends_on": [], "trigger_rule": "all_success"},
    {
        "id": "b",
        "label": "Paso B",
        "action": "upload_factorial",
        "params": {},
        "depends_on": ["a"],
        "trigger_rule": "all_success",
    },
]


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


def test_admin_can_update_an_existing_workflow(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")

    created = client.post("/workflows", json={"name": "Flujo 1", "steps": _SIMPLE_STEPS}).json()
    workflow_id, created_at = created["id"], created["created_at"]

    new_steps = [
        {"id": "a", "label": "Paso A", "action": "extract_bc", "params": {}, "depends_on": [], "trigger_rule": "all_success"},
        {"id": "b", "label": "Paso B", "action": "upload_bc", "params": {}, "depends_on": ["a"], "trigger_rule": "all_success"},
    ]
    updated = client.patch(f"/workflows/{workflow_id}", json={"name": "Flujo 1 renombrado", "steps": new_steps})
    assert updated.status_code == 200
    body = updated.json()
    assert body["id"] == workflow_id
    assert body["name"] == "Flujo 1 renombrado"
    assert len(body["steps"]) == 2
    # id and created_at are preserved -- schedules/history referencing this
    # workflow_id (and the original creation timestamp) must stay valid.
    assert body["created_at"] == created_at

    listed = client.get("/workflows").json()["items"]
    assert len(listed) == 1
    assert listed[0]["name"] == "Flujo 1 renombrado"


def test_update_unknown_workflow_is_404(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")

    resp = client.patch("/workflows/does-not-exist", json={"name": "X", "steps": _SIMPLE_STEPS})
    assert resp.status_code == 404


def test_update_with_cyclic_steps_is_rejected(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    workflow_id = client.post("/workflows", json={"name": "Flujo 1", "steps": _SIMPLE_STEPS}).json()["id"]

    cyclic_steps = [
        {"id": "a", "label": "A", "action": "extract_bc", "params": {}, "depends_on": ["b"], "trigger_rule": "all_success"},
        {"id": "b", "label": "B", "action": "extract_bc", "params": {}, "depends_on": ["a"], "trigger_rule": "all_success"},
    ]
    resp = client.patch(f"/workflows/{workflow_id}", json={"name": "Cíclico", "steps": cyclic_steps})
    assert resp.status_code == 400


def test_operator_cannot_update_workflow(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    workflow_id = client.post("/workflows", json={"name": "Flujo 1", "steps": _SIMPLE_STEPS}).json()["id"]

    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    resp = client.patch(f"/workflows/{workflow_id}", json={"name": "Intento", "steps": _SIMPLE_STEPS})
    assert resp.status_code == 403


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


def test_run_workflow_notify_flag_reaches_the_run(isolated_state, client, fake_subprocess):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    workflow_id = client.post("/workflows", json={"name": "Flujo 1", "steps": _SIMPLE_STEPS}).json()["id"]

    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    run = client.post(f"/workflows/{workflow_id}/run", json={"notify": True})
    assert run.status_code == 200
    run_id = run.json()["id"]

    assert workflow_engine.get_run(run_id).notify is True


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


# --------------------------------------------------------------------------------------
# Reader access: a Reader can only see/launch a workflow an admin explicitly
# assigned them to (e.g. one RRHH user, one Compras user, each with their own
# flow) -- Operator/Admin are never affected by this list.
# --------------------------------------------------------------------------------------


def test_new_workflow_has_no_reader_access_by_default(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    created = client.post("/workflows", json={"name": "Flujo 1", "steps": _SIMPLE_STEPS}).json()
    assert created["reader_allowed_users"] == []


def test_operator_cannot_set_reader_access(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    workflow_id = client.post("/workflows", json={"name": "Flujo 1", "steps": _SIMPLE_STEPS}).json()["id"]

    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")
    resp = client.patch(f"/workflows/{workflow_id}/reader-access", json={"reader_usernames": ["reader1"]})
    assert resp.status_code == 403


def test_set_reader_access_on_unknown_workflow_is_404(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    resp = client.patch("/workflows/does-not-exist/reader-access", json={"reader_usernames": ["reader1"]})
    assert resp.status_code == 404


def test_admin_can_assign_and_clear_reader_access(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    workflow_id = client.post("/workflows", json={"name": "Flujo RRHH", "steps": _SIMPLE_STEPS}).json()["id"]

    granted = client.patch(f"/workflows/{workflow_id}/reader-access", json={"reader_usernames": ["rrhh1", "rrhh1", " "]})
    assert granted.status_code == 200
    assert granted.json()["reader_allowed_users"] == ["rrhh1"]  # de-duplicated, blanks dropped

    cleared = client.patch(f"/workflows/{workflow_id}/reader-access", json={"reader_usernames": []})
    assert cleared.json()["reader_allowed_users"] == []


def test_reader_only_sees_workflows_they_are_assigned_to(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    rrhh_flow = client.post("/workflows", json={"name": "Flujo RRHH", "steps": _SIMPLE_STEPS}).json()["id"]
    compras_flow = client.post("/workflows", json={"name": "Flujo Compras", "steps": _SIMPLE_STEPS}).json()["id"]
    client.patch(f"/workflows/{rrhh_flow}/reader-access", json={"reader_usernames": ["rrhh1"]})
    client.patch(f"/workflows/{compras_flow}/reader-access", json={"reader_usernames": ["compras1"]})

    # Operator/Admin are unaffected -- they still see every workflow.
    all_names = {w["name"] for w in client.get("/workflows").json()["items"]}
    assert all_names == {"Flujo RRHH", "Flujo Compras"}

    make_user("rrhh1", "RrhhPass2026!", users_db.ROLE_READER)
    _login(client, "rrhh1", "RrhhPass2026!")
    rrhh_visible = {w["name"] for w in client.get("/workflows").json()["items"]}
    assert rrhh_visible == {"Flujo RRHH"}


def test_reader_cannot_run_workflow_without_access(isolated_state, client, fake_subprocess):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    workflow_id = client.post("/workflows", json={"name": "Flujo 1", "steps": _SIMPLE_STEPS}).json()["id"]

    make_user("reader1", "ReaderPass2026!", users_db.ROLE_READER)
    _login(client, "reader1", "ReaderPass2026!")
    resp = client.post(f"/workflows/{workflow_id}/run")
    assert resp.status_code == 403


def test_reader_can_run_workflow_they_are_assigned_to(isolated_state, client, fake_subprocess):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    workflow_id = client.post("/workflows", json={"name": "Flujo 1", "steps": _SIMPLE_STEPS}).json()["id"]
    client.patch(f"/workflows/{workflow_id}/reader-access", json={"reader_usernames": ["reader1"]})

    make_user("reader1", "ReaderPass2026!", users_db.ROLE_READER)
    _login(client, "reader1", "ReaderPass2026!")
    resp = client.post(f"/workflows/{workflow_id}/run")
    assert resp.status_code == 200
    assert resp.json()["triggered_by"] == "reader1"


# --------------------------------------------------------------------------------------
# Retry: re-runs only the step(s) that failed (plus anything cascade-cancelled
# because of them), keeping already-"ok" steps' results.
# --------------------------------------------------------------------------------------


def _wait_until_settled(client, run_id, timeout=20.0):
    deadline = time.time() + timeout
    current = None
    while time.time() < deadline:
        items = client.get("/workflow-runs").json()["items"]
        current = next(r for r in items if r["id"] == run_id)
        if current["status"] != "running":
            return current
        time.sleep(0.2)
    raise AssertionError(f"timed out waiting for run to settle; last seen: {current}")


def test_operator_can_retry_the_failed_step_of_a_workflow_run(isolated_state, client, monkeypatch):
    should_fail = {"b": True}

    def _fake_popen(module, argv):
        exit_code = 1 if module == "src.factorial_client.push" and should_fail["b"] else 0
        return subprocess.Popen(
            [sys.executable, "-c", f"import sys; sys.exit({exit_code})"],
            cwd=str(_PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

    monkeypatch.setattr(tasks, "_popen", _fake_popen)

    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    workflow_id = client.post("/workflows", json={"name": "Flujo Retry", "steps": _RETRY_STEPS}).json()["id"]

    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")
    run_id = client.post(f"/workflows/{workflow_id}/run").json()["id"]

    first_result = _wait_until_settled(client, run_id)
    assert first_result["status"] == "error"
    steps_by_id = {s["id"]: s for s in first_result["steps"]}
    assert steps_by_id["a"]["status"] == "ok"
    assert steps_by_id["b"]["status"] == "error"

    # Fix the underlying problem, then retry -- only step "b" should re-run.
    should_fail["b"] = False
    retry_resp = client.post(f"/workflow-runs/{run_id}/retry")
    assert retry_resp.status_code == 200
    assert retry_resp.json()["status"] == "running"

    final_result = _wait_until_settled(client, run_id)
    assert final_result["status"] == "ok"
    final_steps = {s["id"]: s for s in final_result["steps"]}
    assert final_steps["a"]["status"] == "ok"
    assert final_steps["b"]["status"] == "ok"


def test_retry_requires_operator_or_admin_role(isolated_state, client, fake_subprocess):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    workflow_id = client.post("/workflows", json={"name": "Flujo 1", "steps": _SIMPLE_STEPS}).json()["id"]
    client.patch(f"/workflows/{workflow_id}/reader-access", json={"reader_usernames": ["reader1"]})

    make_user("reader1", "ReaderPass2026!", users_db.ROLE_READER)
    _login(client, "reader1", "ReaderPass2026!")
    run_id = client.post(f"/workflows/{workflow_id}/run").json()["id"]

    resp = client.post(f"/workflow-runs/{run_id}/retry")
    assert resp.status_code == 403


def test_retry_is_rejected_for_a_run_that_finished_ok(isolated_state, client, fake_subprocess):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    workflow_id = client.post("/workflows", json={"name": "Flujo 1", "steps": _SIMPLE_STEPS}).json()["id"]

    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")
    run_id = client.post(f"/workflows/{workflow_id}/run").json()["id"]
    _wait_until_settled(client, run_id)

    resp = client.post(f"/workflow-runs/{run_id}/retry")
    assert resp.status_code == 409
