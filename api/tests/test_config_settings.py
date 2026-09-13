# -*- coding: utf-8 -*-
from __future__ import annotations

import json

import pytest

from webapp import users_db
from webapp.tests.conftest import make_user

_BASE_CONFIG = {
    "business_central": {
        "tenant_id": "old-tenant",
        "client_id": "old-bc-client",
        "scope": "https://api.businesscentral.dynamics.com/.default",
        "token_url": "https://login.microsoftonline.com/old-tenant/oauth2/v2.0/token",
        "company_name": "CADE Soluciones",
        "page_size": 1000,
        "output_dir": "./exports",
    },
    "business_central_upload": {
        "tenant_id": "old-tenant",
        "client_id": "old-upload-client",
        "workspace_id": "ws-1",
        "workspace_name": "Sandbox",
        "lakehouse_id": "lh-1",
        "lakehouse_name": "Lakehouse",
        "max_retries": 3,
        "enabled": True,
        "overwrite": True,
    },
    "factorial_upload": {
        "tenant_id": "old-tenant",
        "client_id": "old-upload-client",
        "workspace_id": "ws-1",
        "workspace_name": "Sandbox",
        "lakehouse_id": "lh-1",
        "lakehouse_name": "Lakehouse",
        "max_retries": 3,
    },
    "hubspot_upload": {
        "tenant_id": "old-tenant",
        "client_id": "old-upload-client",
        "workspace_id": "ws-1",
        "workspace_name": "Sandbox",
        "lakehouse_id": "lh-1",
        "lakehouse_name": "Lakehouse",
        "max_retries": 3,
    },
    "fabric_pipelines": {"pipelines": [{"name": "Pipeline_CADE", "item_id": "pl-1"}]},
    "notifications": {
        "enabled": False,
        "smtp_host": "",
        "smtp_port": 587,
        "use_tls": True,
        "from_address": "",
        "admin_recipients": [],
    },
}


@pytest.fixture(autouse=True)
def _isolated_config_file(tmp_path, monkeypatch):
    """config.json is never in api/tests/conftest.py's own isolated_state
    (that fixture predates this module) -- isolated here directly instead
    of touching that shared fixture, so every OTHER existing test's
    already-established behavior around config.json stays exactly as-is."""
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(_BASE_CONFIG, indent=2), encoding="utf-8")
    monkeypatch.setenv("CONFIG_FILE", str(config_path))
    yield config_path


def _login(client, username, password):
    assert client.post("/auth/login", json={"username": username, "password": password}).status_code == 200


def test_operator_cannot_list_config_fields(isolated_state, client):
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")
    assert client.get("/admin/config").status_code == 403


def test_admin_lists_config_fields(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    resp = client.get("/admin/config")
    assert resp.status_code == 200
    items = {i["key"]: i for i in resp.json()["items"]}
    assert items["bc_tenant_id"]["value"] == "old-tenant"
    assert items["fabric_upload_enabled"]["value"] is True
    assert items["notifications_admin_recipients"]["value"] == []


def test_admin_can_update_a_shared_upload_field(isolated_state, client, _isolated_config_file):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")

    resp = client.patch("/admin/config/fabric_upload_workspace_id", json={"value": "ws-new"})
    assert resp.status_code == 200
    assert resp.json()["value"] == "ws-new"

    raw = json.loads(_isolated_config_file.read_text(encoding="utf-8"))
    assert raw["business_central_upload"]["workspace_id"] == "ws-new"
    assert raw["factorial_upload"]["workspace_id"] == "ws-new"
    assert raw["hubspot_upload"]["workspace_id"] == "ws-new"


def test_admin_updating_bc_tenant_id_recomputes_token_url(isolated_state, client, _isolated_config_file):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")

    client.patch("/admin/config/bc_tenant_id", json={"value": "new-tenant"})

    raw = json.loads(_isolated_config_file.read_text(encoding="utf-8"))
    assert raw["business_central"]["token_url"] == "https://login.microsoftonline.com/new-tenant/oauth2/v2.0/token"


def test_admin_updating_a_number_field_rejects_non_integer_text(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    resp = client.patch("/admin/config/bc_page_size", json={"value": "not-a-number"})
    assert resp.status_code == 400


def test_operator_cannot_update_a_config_field(isolated_state, client):
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")
    resp = client.patch("/admin/config/bc_company_name", json={"value": "x"})
    assert resp.status_code == 403


def test_rejects_unknown_config_key(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    resp = client.patch("/admin/config/not_a_real_field", json={"value": "x"})
    assert resp.status_code == 400


def test_admin_lists_and_replaces_pipelines(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")

    listed = client.get("/admin/config/pipelines")
    assert listed.status_code == 200
    assert listed.json()["items"] == [{"name": "Pipeline_CADE", "item_id": "pl-1"}]

    resp = client.put(
        "/admin/config/pipelines",
        json={"items": [{"name": "Pipeline_CADE_Gold", "item_id": "pl-9"}]},
    )
    assert resp.status_code == 200
    assert resp.json()["items"] == [{"name": "Pipeline_CADE_Gold", "item_id": "pl-9"}]

    listed2 = client.get("/admin/config/pipelines")
    assert listed2.json()["items"] == [{"name": "Pipeline_CADE_Gold", "item_id": "pl-9"}]


def test_admin_setting_pipelines_rejects_a_blank_item_id(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")
    resp = client.put("/admin/config/pipelines", json={"items": [{"name": "Foo", "item_id": ""}]})
    assert resp.status_code == 400


def test_operator_cannot_set_pipelines(isolated_state, client):
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")
    resp = client.put("/admin/config/pipelines", json={"items": []})
    assert resp.status_code == 403
