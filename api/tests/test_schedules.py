# -*- coding: utf-8 -*-
from __future__ import annotations

from webapp import users_db
from webapp.tests.conftest import make_user


def _login(client, username, password):
    assert client.post("/auth/login", json={"username": username, "password": password}).status_code == 200


def test_reader_can_list_but_not_create(isolated_state, client):
    make_user("reader1", "ReaderPass2026!", users_db.ROLE_READER)
    _login(client, "reader1", "ReaderPass2026!")

    assert client.get("/schedules").status_code == 200
    resp = client.post(
        "/schedules",
        json={
            "name": "Nightly BC",
            "action": "extract_bc",
            "params": {},
            "trigger": "interval",
            "trigger_args": {"hours": 24},
        },
    )
    assert resp.status_code == 403


def test_admin_can_create_pause_and_delete_a_schedule(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")

    created = client.post(
        "/schedules",
        json={
            "name": "Nightly BC",
            "action": "extract_bc",
            "params": {},
            "trigger": "interval",
            "trigger_args": {"hours": 24},
        },
    )
    assert created.status_code == 200
    schedule_id = created.json()["id"]
    assert created.json()["enabled"] is True
    # A live scheduler backs this endpoint (see conftest's `client` fixture),
    # so creating a schedule must immediately compute its next fire time.
    assert created.json()["next_run_time"] is not None
    assert created.json()["missed_last_run"] is False

    paused = client.patch(f"/schedules/{schedule_id}", json={"enabled": False})
    assert paused.status_code == 204

    schedules = client.get("/schedules").json()["items"]
    paused_schedule = next(s for s in schedules if s["id"] == schedule_id)
    assert paused_schedule["enabled"] is False
    assert paused_schedule["next_run_time"] is None

    deleted = client.delete(f"/schedules/{schedule_id}")
    assert deleted.status_code == 204
    assert client.get("/schedules").json()["items"] == []


def test_reader_cannot_update_a_schedule(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    created = client.post(
        "/schedules",
        json={"name": "Nightly BC", "action": "extract_bc", "params": {}, "trigger": "interval", "trigger_args": {"hours": 24}},
    ).json()

    make_user("reader1", "ReaderPass2026!", users_db.ROLE_READER)
    _login(client, "reader1", "ReaderPass2026!")
    resp = client.put(
        f"/schedules/{created['id']}",
        json={"name": "x", "action": "extract_bc", "params": {}, "trigger": "interval", "trigger_args": {"hours": 1}},
    )
    assert resp.status_code == 403


def test_admin_can_update_an_existing_schedule(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")

    created = client.post(
        "/schedules",
        json={
            "name": "Nightly BC",
            "action": "extract_bc",
            "params": {},
            "trigger": "interval",
            "trigger_args": {"hours": 24},
        },
    ).json()
    schedule_id, created_at = created["id"], created["created_at"]

    updated = client.put(
        f"/schedules/{schedule_id}",
        json={
            "name": "Nightly BC renombrada",
            "action": "sync_bc",
            "params": {"mode": "incremental", "parallel": 2},
            "trigger": "interval",
            "trigger_args": {"hours": 12},
        },
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["id"] == schedule_id
    assert body["name"] == "Nightly BC renombrada"
    assert body["action"] == "sync_bc"
    assert body["params"] == {"mode": "incremental", "parallel": 2}
    assert body["trigger_args"] == {"hours": 12}
    # id, created_at and enabled state are preserved -- history/other
    # references to this schedule_id stay valid after the edit.
    assert body["created_at"] == created_at
    assert body["enabled"] is True
    # A live scheduler backs this endpoint -- the new trigger config must
    # already be reflected in the recomputed next_run_time.
    assert body["next_run_time"] is not None


def test_updating_a_paused_schedule_keeps_it_paused(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")

    created = client.post(
        "/schedules",
        json={"name": "Nightly BC", "action": "extract_bc", "params": {}, "trigger": "interval", "trigger_args": {"hours": 24}},
    ).json()
    schedule_id = created["id"]
    client.patch(f"/schedules/{schedule_id}", json={"enabled": False})

    updated = client.put(
        f"/schedules/{schedule_id}",
        json={"name": "Nightly BC", "action": "extract_bc", "params": {}, "trigger": "interval", "trigger_args": {"hours": 6}},
    )
    assert updated.status_code == 200
    assert updated.json()["enabled"] is False
    assert updated.json()["next_run_time"] is None


def test_update_unknown_schedule_is_404(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")

    resp = client.put(
        "/schedules/does-not-exist",
        json={"name": "x", "action": "extract_bc", "params": {}, "trigger": "interval", "trigger_args": {"hours": 1}},
    )
    assert resp.status_code == 404


def test_update_schedule_rejects_invalid_cron(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    created = client.post(
        "/schedules",
        json={"name": "Nightly BC", "action": "extract_bc", "params": {}, "trigger": "interval", "trigger_args": {"hours": 24}},
    ).json()

    resp = client.put(
        f"/schedules/{created['id']}",
        json={"name": "x", "action": "extract_bc", "params": {}, "trigger": "cron", "trigger_args": {"expr": "not a cron"}},
    )
    assert resp.status_code == 400


def test_invalid_cron_expression_is_rejected(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")

    resp = client.post(
        "/schedules",
        json={
            "name": "Bad cron",
            "action": "extract_bc",
            "params": {},
            "trigger": "cron",
            "trigger_args": {"expr": "not a cron expression"},
        },
    )
    assert resp.status_code == 400


def test_schedules_week_reflects_a_created_schedule(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")

    create = client.post(
        "/schedules",
        json={
            "name": "Nightly BC",
            "action": "extract_bc",
            "params": {},
            "trigger": "interval",
            "trigger_args": {"hours": 24},
        },
    )
    schedule_id = create.json()["id"]

    resp = client.get("/schedules/week")
    assert resp.status_code == 200
    occurrences = resp.json()["occurrences"]
    assert schedule_id in occurrences
