# -*- coding: utf-8 -*-
from __future__ import annotations

import os

import pytest

from webapp import users_db
from webapp.tests.conftest import make_user


def _login(client, username, password):
    assert client.post("/auth/login", json={"username": username, "password": password}).status_code == 200


@pytest.fixture(autouse=True)
def _restore_os_environ_mutations():
    """set_field() intentionally mirrors into os.environ directly (see
    webapp/env_secrets.py) so the change takes effect immediately -- that's
    a real, deliberate side effect outside pytest's monkeypatch tracking,
    so tests that trigger it must restore os.environ themselves."""
    before = dict(os.environ)
    yield
    for key in set(os.environ) - set(before):
        del os.environ[key]
    os.environ.update(before)


def test_operator_cannot_list_secrets(isolated_state, client):
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")
    resp = client.get("/admin/secrets")
    assert resp.status_code == 403


def test_admin_lists_known_fields_with_empty_values_when_env_missing(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    resp = client.get("/admin/secrets")
    assert resp.status_code == 200
    items = resp.json()["items"]
    keys = [i["key"] for i in items]
    assert "BC_CLIENT_SECRET" in keys
    assert "HUBSPOT_API_KEY" in keys
    assert all(i["value"] == "" for i in items)


def test_admin_can_set_and_read_back_a_field(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")

    resp = client.patch("/admin/secrets/HUBSPOT_API_KEY", json={"value": "pat-eu1-test"})
    assert resp.status_code == 200
    assert resp.json()["value"] == "pat-eu1-test"

    listed = client.get("/admin/secrets").json()["items"]
    hubspot = next(i for i in listed if i["key"] == "HUBSPOT_API_KEY")
    assert hubspot["value"] == "pat-eu1-test"
    assert os.environ["HUBSPOT_API_KEY"] == "pat-eu1-test"


def test_setting_bc_environment_persists_and_mirrors_into_os_environ(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")

    resp = client.patch("/admin/secrets/BC_ENVIRONMENT", json={"value": "SANDBOX"})
    assert resp.status_code == 200
    assert resp.json()["value"] == "SANDBOX"
    assert os.environ["BC_ENVIRONMENT"] == "SANDBOX"

    listed = client.get("/admin/secrets").json()["items"]
    bc_env = next(i for i in listed if i["key"] == "BC_ENVIRONMENT")
    assert bc_env["value"] == "SANDBOX"


def test_rejects_unknown_key(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    resp = client.patch("/admin/secrets/SOME_RANDOM_VAR", json={"value": "x"})
    assert resp.status_code == 400


def test_operator_cannot_set_a_field(isolated_state, client):
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")
    resp = client.patch("/admin/secrets/HUBSPOT_API_KEY", json={"value": "x"})
    assert resp.status_code == 403


def test_operator_cannot_test_connections(isolated_state, client):
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")
    for path in (
        "/admin/secrets/test/business-central",
        "/admin/secrets/test/factorial",
        "/admin/secrets/test/hubspot",
        "/admin/secrets/test/fabric",
    ):
        assert client.post(path).status_code == 403


def test_admin_test_connection_reports_failure_without_crashing_when_unconfigured(
    isolated_state, client, monkeypatch
):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    # Force the missing-secret path deterministically -- otherwise this test's
    # outcome would depend on whatever HUBSPOT_API_KEY happens to already be
    # in os.environ from the real .env (e.g. loaded by some other test's bare
    # load_dotenv() call earlier in the same session), which could make this
    # actually reach the live HubSpot API instead of failing cleanly.
    monkeypatch.delenv("HUBSPOT_API_KEY", raising=False)
    resp = client.post("/admin/secrets/test/hubspot")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["message"]
