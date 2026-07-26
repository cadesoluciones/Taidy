# -*- coding: utf-8 -*-
from __future__ import annotations

from api import session_store
from webapp import users_db
from webapp.tests.conftest import make_user


def _login(client, username, password):
    assert client.post("/auth/login", json={"username": username, "password": password}).status_code == 200


def test_reader_cannot_list_users(isolated_state, client):
    make_user("reader1", "ReaderPass2026!", users_db.ROLE_READER)
    _login(client, "reader1", "ReaderPass2026!")
    assert client.get("/users").status_code == 403


def test_admin_can_create_and_list_users(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")

    resp = client.post("/users", json={"username": "carlos", "password": "Temporal2026!", "role": users_db.ROLE_OPERATOR})
    assert resp.status_code == 200
    assert resp.json()["must_change_password"] is True

    usernames = [u["username"] for u in client.get("/users").json()["items"]]
    assert "carlos" in usernames


def test_change_role_protects_last_admin(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    # admin2 is the only OTHER admin besides the default "admin" -- demote
    # the default admin down to reader, leaving admin2 as the last admin,
    # then try to demote admin2 too: must be rejected.
    users_db.set_role("admin", users_db.ROLE_READER)

    resp = client.patch("/users/admin2/role", json={"role": users_db.ROLE_READER})
    assert resp.status_code == 400


def test_delete_user(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    make_user("carlos", "Temporal2026!", users_db.ROLE_OPERATOR)
    _login(client, "admin2", "AdminPass2026!")

    resp = client.delete("/users/carlos")
    assert resp.status_code == 204
    assert users_db.get_user("carlos") is None


def test_reader_cannot_list_sessions(isolated_state, client):
    make_user("reader1", "ReaderPass2026!", users_db.ROLE_READER)
    _login(client, "reader1", "ReaderPass2026!")
    assert client.get("/users/reader1/sessions").status_code == 403


def test_operator_cannot_revoke_a_session(isolated_state, client):
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")
    assert client.delete("/users/operator1/sessions/abc123456789").status_code == 403


def test_admin_can_list_and_revoke_a_users_session(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")  # creates operator1's session

    _login(client, "admin2", "AdminPass2026!")  # switches this client's cookie to admin2's
    sessions = client.get("/users/operator1/sessions").json()["items"]
    assert len(sessions) == 1
    assert "session_ref" in sessions[0]

    resp = client.delete(f"/users/operator1/sessions/{sessions[0]['session_ref']}")
    assert resp.status_code == 204
    assert session_store.list_sessions_for_user("operator1") == []


def test_revoking_an_unknown_session_ref_is_a_no_op(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")

    resp = client.delete("/users/admin2/sessions/does-not-exist")
    assert resp.status_code == 204
