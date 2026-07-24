# -*- coding: utf-8 -*-
from __future__ import annotations

from webapp import users_db
from webapp.tests.conftest import make_user


def _login(client, username, password):
    assert client.post("/auth/login", json={"username": username, "password": password}).status_code == 200


def test_audit_requires_admin(isolated_state, client):
    make_user("reader1", "ReaderPass2026!", users_db.ROLE_READER)
    _login(client, "reader1", "ReaderPass2026!")

    resp = client.get("/audit")
    assert resp.status_code == 403


def test_admin_sees_audit_log_of_the_login_that_just_happened(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")

    resp = client.get("/audit")
    assert resp.status_code == 200
    events = [e["event"] for e in resp.json()["items"]]
    assert "login" in events
