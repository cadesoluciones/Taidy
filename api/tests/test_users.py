# -*- coding: utf-8 -*-
from __future__ import annotations

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
