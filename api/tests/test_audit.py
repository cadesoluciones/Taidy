# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import io

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


def test_a_denied_role_check_is_itself_recorded_in_the_audit_log(isolated_state, client):
    """require_role()/require_any_role() (api/dependencies.py) reject with a
    plain 403 -- this proves the rejection also writes an "authorization"
    audit entry, the same event type the retired Streamlit app recorded on
    every denied role check."""
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")
    assert client.post("/users", json={"username": "x", "password": "Xxxxxxxx1!", "role": "App.Reader"}).status_code == 403

    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    entries = client.get("/audit").json()["items"]
    authz_denials = [e for e in entries if e["event"] == "authorization" and e["user"] == "operator1"]
    assert len(authz_denials) == 1
    assert authz_denials[0]["outcome"] == "denied"


def test_export_csv_requires_admin(isolated_state, client):
    make_user("reader1", "ReaderPass2026!", users_db.ROLE_READER)
    _login(client, "reader1", "ReaderPass2026!")

    resp = client.get("/audit/export.csv")
    assert resp.status_code == 403


def test_export_csv_contains_the_login_that_just_happened(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")

    resp = client.get("/audit/export.csv")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert 'filename="auditoria.csv"' in resp.headers["content-disposition"]

    body = resp.text
    header, *rows = body.strip().splitlines()
    assert header == "Fecha,Evento,Resultado,Usuario,Detalle"
    assert any("login" in row and "admin2" in row for row in rows)


def test_export_csv_respects_the_same_filters_as_the_json_endpoint(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")

    resp = client.get("/audit/export.csv", params={"event": "login"})
    reader = csv.DictReader(io.StringIO(resp.text))
    rows = list(reader)
    assert len(rows) >= 1
    assert all(row["Evento"] == "login" for row in rows)
