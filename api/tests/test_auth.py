# -*- coding: utf-8 -*-
"""
First vertical slice of the migration: proves the whole chain (HTTP request
-> FastAPI -> the SAME users_db.py the Streamlit app already uses -> SQLite)
works end-to-end, and that the forced-password-change gate (F-02) and the
never-trust-a-cached-role invariant (F-04) both carry over from the
Streamlit app's auth.py.
"""

from __future__ import annotations

from webapp import users_db
from webapp.tests.conftest import make_user

from api.dependencies import SESSION_COOKIE_NAME


def test_login_success_returns_role_and_sets_cookie(isolated_state, client):
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)

    resp = client.post("/auth/login", json={"username": "operator1", "password": "OperatorPass2026!"})

    assert resp.status_code == 200
    body = resp.json()
    assert body == {"username": "operator1", "role": users_db.ROLE_OPERATOR, "must_change_password": False}
    assert SESSION_COOKIE_NAME in resp.cookies


def test_login_wrong_password_is_401(isolated_state, client):
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)

    resp = client.post("/auth/login", json={"username": "operator1", "password": "wrong"})

    assert resp.status_code == 401
    assert SESSION_COOKIE_NAME not in resp.cookies


def test_login_unknown_user_is_401(isolated_state, client):
    resp = client.post("/auth/login", json={"username": "ghost", "password": "whatever1"})
    assert resp.status_code == 401


def test_me_without_session_is_401(isolated_state, client):
    resp = client.get("/auth/me")
    assert resp.status_code == 401


def test_logout_clears_session(isolated_state, client):
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    client.post("/auth/login", json={"username": "operator1", "password": "OperatorPass2026!"})

    resp = client.post("/auth/logout")
    assert resp.status_code == 204

    # The cookie the client still holds is now unknown server-side.
    resp = client.get("/auth/me")
    assert resp.status_code == 401


def test_forced_password_change_flow(isolated_state, client):
    # A freshly created default admin always has must_change_password=True --
    # this is the exact scenario auth.require_authenticated_user() forces a
    # change-password screen for in the Streamlit app.
    login = client.post("/auth/login", json={"username": "admin", "password": users_db.DEFAULT_ADMIN_PASSWORD})
    assert login.status_code == 200
    assert login.json()["must_change_password"] is True

    me = client.get("/auth/me")
    assert me.json()["must_change_password"] is True

    changed = client.post(
        "/auth/change-password",
        json={"new_password": "BrandNewPass2026!", "confirm_password": "BrandNewPass2026!"},
    )
    assert changed.status_code == 200
    assert changed.json()["must_change_password"] is False

    me_after = client.get("/auth/me")
    assert me_after.json()["must_change_password"] is False


def test_change_password_mismatch_is_400(isolated_state, client):
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    client.post("/auth/login", json={"username": "operator1", "password": "OperatorPass2026!"})

    resp = client.post(
        "/auth/change-password",
        json={"new_password": "NewPassword2026!", "confirm_password": "Different2026!"},
    )
    assert resp.status_code == 400


def test_role_stays_fresh_after_admin_changes_it_mid_session(isolated_state, client):
    """F-04: the API must re-check the role from the DB on every request, not
    trust whatever role a session was created with -- this is a REST-context
    strengthening of the same invariant auth.py already documents for
    Streamlit (there it re-reads on every script rerun; here, every request).
    """
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    client.post("/auth/login", json={"username": "operator1", "password": "OperatorPass2026!"})
    assert client.get("/auth/me").json()["role"] == users_db.ROLE_OPERATOR

    users_db.set_role("operator1", users_db.ROLE_ADMIN)

    assert client.get("/auth/me").json()["role"] == users_db.ROLE_ADMIN
