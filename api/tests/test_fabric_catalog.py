# -*- coding: utf-8 -*-
from __future__ import annotations

from webapp import users_db
from webapp.tests.conftest import make_user

from api.routers import fabric_catalog as fabric_catalog_router

_EMPTY_PAYLOAD = {
    "short_description": "",
    "long_description_markdown": "",
    "owners": [],
    "criticality": "",
    "status": "",
    "tags": [],
    "relationships": [],
}


def _login(client, username, password):
    assert client.post("/auth/login", json={"username": username, "password": password}).status_code == 200


class _FakeFabricClient:
    def list_items(self):
        return [
            {"id": "nb-1", "type": "Notebook", "displayName": "silver_facturas", "folderId": "f-silver"},
            {"id": "pl-1", "type": "DataPipeline", "displayName": "Pipeline_CADE_Bronce"},
        ]

    def list_folders(self):
        return [
            {"id": "f-root", "displayName": "ETLs Medallion"},
            {"id": "f-silver", "displayName": "silver", "parentFolderId": "f-root"},
        ]


def _use_fake_fabric_client(monkeypatch):
    monkeypatch.setattr(fabric_catalog_router, "_client", lambda: _FakeFabricClient())


def test_reader_cannot_list_catalog_items(isolated_state, client, monkeypatch):
    """Gobernanza de datos lives under Catalogo de datos, which is
    Operator/Admin-only at the route level -- Reader never even sees the
    nav entry, so the API is gated the same way, not just the write path."""
    _use_fake_fabric_client(monkeypatch)
    make_user("reader1", "ReaderPass2026!", users_db.ROLE_READER)
    _login(client, "reader1", "ReaderPass2026!")

    resp = client.get("/fabric-catalog/items")
    assert resp.status_code == 403


def test_operator_can_list_catalog_items(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    resp = client.get("/fabric-catalog/items")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert {i["item_id"] for i in items} == {"nb-1", "pl-1"}
    notebook = next(i for i in items if i["item_id"] == "nb-1")
    assert notebook["folder_path"] == ["ETLs Medallion", "silver"]
    assert notebook["short_description"] == ""
    assert notebook["owners"] == []
    assert notebook["tags"] == []
    assert notebook["reviewed_by"] == ""


def test_reader_cannot_update_catalog_item(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("reader1", "ReaderPass2026!", users_db.ROLE_READER)
    _login(client, "reader1", "ReaderPass2026!")

    resp = client.patch("/fabric-catalog/items/nb-1", json=_EMPTY_PAYLOAD)
    assert resp.status_code == 403


def test_operator_can_update_catalog_item(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    resp = client.patch(
        "/fabric-catalog/items/nb-1",
        json={
            **_EMPTY_PAYLOAD,
            "short_description": "Facturas consolidadas desde bronze",
            "long_description_markdown": "# Facturas\nConsolidado **diario**.",
            "owners": ["jose"],
            "criticality": "alta",
            "status": "activo",
            "tags": ["finanzas"],
            "relationships": [{"type": "reads_from", "target_item_id": "lh-bronze"}],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["short_description"] == "Facturas consolidadas desde bronze"
    assert body["long_description_markdown"] == "# Facturas\nConsolidado **diario**."
    assert body["owners"] == ["jose"]
    assert body["criticality"] == "alta"
    assert body["status"] == "activo"
    assert body["tags"] == ["finanzas"]
    assert body["relationships"] == [{"type": "reads_from", "target_item_id": "lh-bronze"}]
    assert body["reviewed_by"] == "operator1"
    assert body["reviewed_at"] != ""

    listed = client.get("/fabric-catalog/items").json()["items"]
    notebook = next(i for i in listed if i["item_id"] == "nb-1")
    assert notebook["short_description"] == "Facturas consolidadas desde bronze"
    assert notebook["reviewed_by"] == "operator1"


def test_admin_can_update_catalog_item(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")

    resp = client.patch(
        "/fabric-catalog/items/pl-1",
        json={**_EMPTY_PAYLOAD, "short_description": "Pipeline bronce"},
    )
    assert resp.status_code == 200
    assert resp.json()["reviewed_by"] == "admin2"


def test_update_rejects_an_invalid_relationship_type(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")

    resp = client.patch(
        "/fabric-catalog/items/nb-1",
        json={**_EMPTY_PAYLOAD, "relationships": [{"type": "not_a_real_type", "target_item_id": "x"}]},
    )
    assert resp.status_code == 400


def test_update_rejects_an_invalid_criticality(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")

    resp = client.patch(
        "/fabric-catalog/items/nb-1",
        json={**_EMPTY_PAYLOAD, "criticality": "urgentisimo"},
    )
    assert resp.status_code == 400


def test_unauthenticated_cannot_list_catalog_items(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    resp = client.get("/fabric-catalog/items")
    assert resp.status_code == 401


def test_operator_can_create_and_list_a_custom_item(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    resp = client.post("/fabric-catalog/custom-items", json={"name": "Excel de ventas", "type": "Fuente externa"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Excel de ventas"
    assert body["type"] == "Fuente externa"
    assert body["folder_path"] == ["Personalizados"]
    assert body["is_custom"] is True
    assert body["reviewed_by"] == "operator1"
    item_id = body["item_id"]

    listed = client.get("/fabric-catalog/items").json()["items"]
    assert any(i["item_id"] == item_id and i["is_custom"] for i in listed)


def test_reader_cannot_create_a_custom_item(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("reader1", "ReaderPass2026!", users_db.ROLE_READER)
    _login(client, "reader1", "ReaderPass2026!")

    resp = client.post("/fabric-catalog/custom-items", json={"name": "Excel de ventas", "type": ""})
    assert resp.status_code == 403


def test_create_custom_item_rejects_a_blank_name(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    resp = client.post("/fabric-catalog/custom-items", json={"name": "   ", "type": ""})
    assert resp.status_code == 400


def test_admin_can_delete_a_custom_item(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")

    created = client.post("/fabric-catalog/custom-items", json={"name": "Excel de ventas", "type": ""}).json()
    resp = client.delete(f"/fabric-catalog/custom-items/{created['item_id']}")
    assert resp.status_code == 204

    listed = client.get("/fabric-catalog/items").json()["items"]
    assert all(i["item_id"] != created["item_id"] for i in listed)


def test_delete_custom_item_rejects_an_unknown_id(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")

    resp = client.delete("/fabric-catalog/custom-items/custom:does-not-exist")
    assert resp.status_code == 400
