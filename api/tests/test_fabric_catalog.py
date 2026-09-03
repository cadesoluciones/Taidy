# -*- coding: utf-8 -*-
from __future__ import annotations

import base64

from src.fabric_pipelines.api import FabricPipelineError
from webapp import fabric_catalog, users_db
from webapp.tests.conftest import make_user

from api.routers import fabric_catalog as fabric_catalog_router

_EMPTY_PAYLOAD = {
    "short_description": "",
    "long_description_markdown": "",
    "data_owner": [],
    "data_steward": [],
    "data_custodian": [],
    "data_consumer": [],
    "criticality": "",
    "status": "",
    "tags": [],
    "relationships": [],
}


def _login(client, username, password):
    assert client.post("/auth/login", json={"username": username, "password": password}).status_code == 200


class _FakeFabricClient:
    def __init__(self):
        self.workspace_id = "ws-fake"
        self._extra_items = {}  # {item_id: item} -- e.g. semantic models created via create_item()
        self._lakehouse_columns = {("lh-1", "bronze", "ventas"): [{"name": "id", "sql_type": "int"}]}
        self._model_definitions = {}
        self._next_id = 1
        self._lakehouse_files = {}  # {(lakehouse_item_id, path): "content"}
        self._lakehouse_tables = {}  # {lakehouse_item_id: [{"schema": ..., "table": ...}, ...]}

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

    def get_item(self, item_id):
        if item_id in self._extra_items:
            return self._extra_items[item_id]
        if item_id in self._model_definitions:
            raise FabricPipelineError("model deleted")
        return {"id": "lh-1", "type": "Lakehouse", "displayName": "Lakehouse"}

    def preview_lakehouse_table(self, item_id, display_name, schema, table, limit=10):
        return {"columns": ["id", "name"], "rows": [["1", "Alice"], ["2", "Bob"]]}

    def list_lakehouse_table_columns(self, item_id, display_name, schema, table):
        return self._lakehouse_columns.get((item_id, schema, table), [])

    def list_lakehouse_tables(self, item_id, display_name):
        return self._lakehouse_tables.get(item_id, [])

    def create_item(self, display_name, item_type, parts):
        item_id = f"model-{self._next_id}"
        self._next_id += 1
        self._model_definitions[item_id] = parts
        self._extra_items[item_id] = {"id": item_id, "type": item_type, "displayName": display_name}
        return item_id

    def get_definition(self, item_id):
        # .get(..., []) rather than a bare lookup: relationship-detection
        # scans every Notebook's definition regardless of whether a given
        # test cares about it (e.g. the default "nb-1" from list_items()
        # below never gets a definition set up otherwise) -- an empty
        # parts list is a realistic "nothing to parse here" shape, not a
        # test setup bug the way a KeyError would be.
        return {"definition": {"parts": self._model_definitions.get(item_id, [])}}

    def update_item_definition(self, item_id, parts):
        self._model_definitions[item_id] = parts

    def read_lakehouse_file(self, lakehouse_item_id, path):
        return self._lakehouse_files.get((lakehouse_item_id, path))

    def write_lakehouse_file(self, lakehouse_item_id, path, content):
        self._lakehouse_files[(lakehouse_item_id, path)] = content


def _use_fake_fabric_client(monkeypatch):
    # One shared instance for the whole test, not a fresh one per _client()
    # call -- semantic-model tests need state (created models) to survive
    # across several requests within the same test.
    fake = _FakeFabricClient()
    monkeypatch.setattr(fabric_catalog_router, "_client", lambda: fake)
    # Isolate from the project's real tables.yaml/hubspot_tables.yaml/
    # factorial_tables.yaml so item-count/item-id assertions here stay
    # about the two Fabric items this fake client returns, not whatever's
    # really configured.
    monkeypatch.setattr(fabric_catalog.table_configs, "list_bc_tables_full", lambda: [])
    monkeypatch.setattr(fabric_catalog.table_configs, "list_hubspot_tables_full", lambda: [])
    monkeypatch.setattr(fabric_catalog.table_configs, "list_factorial_tables_full", lambda: [])
    return fake


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
    assert notebook["folder_path"] == ["Fabric", "ETLs Medallion", "silver"]
    assert notebook["short_description"] == ""
    assert notebook["data_owner"] == []
    assert notebook["tags"] == []
    assert notebook["reviewed_by"] == ""


def test_list_catalog_items_marks_fabric_items_online_and_bc_items_always_online(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    monkeypatch.setattr(fabric_catalog.table_configs, "list_bc_tables_full", lambda: [{"name": "bc_customer"}])
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    items = client.get("/fabric-catalog/items").json()["items"]
    notebook = next(i for i in items if i["item_id"] == "nb-1")
    assert notebook["connection_status"] == "online"
    assert notebook["last_synced_at"] == ""
    bc_table = next(i for i in items if i["item_id"] == "bc:bc_customer")
    assert bc_table["connection_status"] == "online"


def test_list_catalog_items_offline_item_can_be_deleted_and_reappears_if_seen_again(isolated_state, client, monkeypatch):
    fake = _use_fake_fabric_client(monkeypatch)
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")

    first = client.get("/fabric-catalog/items").json()["items"]
    assert {i["item_id"] for i in first} == {"nb-1", "pl-1"}

    # Fabric stops returning "pl-1" -- e.g. its capacity/license lapsed.
    fake.list_items = lambda: [{"id": "nb-1", "type": "Notebook", "displayName": "silver_facturas", "folderId": "f-silver"}]
    second = client.get("/fabric-catalog/items").json()["items"]
    pipeline = next(i for i in second if i["item_id"] == "pl-1")
    assert pipeline["connection_status"] == "offline"

    resp = client.delete("/fabric-catalog/items/pl-1")
    assert resp.status_code == 204
    third = client.get("/fabric-catalog/items").json()["items"]
    assert "pl-1" not in {i["item_id"] for i in third}

    # It's still a real item Fabric could list again -- coming back live
    # should make it reappear, deleting only ever forgot the local copy.
    fake.list_items = lambda: [
        {"id": "nb-1", "type": "Notebook", "displayName": "silver_facturas", "folderId": "f-silver"},
        {"id": "pl-1", "type": "DataPipeline", "displayName": "Pipeline_CADE_Bronce"},
    ]
    fourth = client.get("/fabric-catalog/items").json()["items"]
    pipeline_again = next(i for i in fourth if i["item_id"] == "pl-1")
    assert pipeline_again["connection_status"] == "online"


def test_delete_offline_item_rejects_a_bc_item(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    monkeypatch.setattr(fabric_catalog.table_configs, "list_bc_tables_full", lambda: [{"name": "bc_customer"}])
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")

    resp = client.delete("/fabric-catalog/items/bc:bc_customer")
    assert resp.status_code == 400


def test_delete_offline_item_rejects_an_unknown_item(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")

    resp = client.delete("/fabric-catalog/items/nb-does-not-exist")
    assert resp.status_code == 400


def test_reader_cannot_delete_an_offline_item(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("reader1", "ReaderPass2026!", users_db.ROLE_READER)
    _login(client, "reader1", "ReaderPass2026!")

    resp = client.delete("/fabric-catalog/items/pl-1")
    assert resp.status_code == 403


def test_list_catalog_items_includes_bc_and_hubspot_tables(isolated_state, client, monkeypatch):
    monkeypatch.setattr(fabric_catalog_router, "_client", lambda: _FakeFabricClient())
    monkeypatch.setattr(
        fabric_catalog.table_configs, "list_bc_tables_full", lambda: [{"name": "bc_customer"}]
    )
    monkeypatch.setattr(
        fabric_catalog.table_configs, "list_hubspot_tables_full", lambda: [{"name": "hubspot_contacts"}]
    )
    monkeypatch.setattr(fabric_catalog.table_configs, "list_factorial_tables_full", lambda: [])
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    items = client.get("/fabric-catalog/items").json()["items"]
    assert {i["item_id"] for i in items} == {"nb-1", "pl-1", "bc:bc_customer", "hubspot:hubspot_contacts"}
    bc_item = next(i for i in items if i["item_id"] == "bc:bc_customer")
    assert bc_item["folder_path"] == ["Business Central"]
    hs_item = next(i for i in items if i["item_id"] == "hubspot:hubspot_contacts")
    assert hs_item["folder_path"] == ["HubSpot"]


def test_list_catalog_items_includes_factorial_tables(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    monkeypatch.setattr(
        fabric_catalog.table_configs, "list_factorial_tables_full", lambda: [{"name": "employees"}]
    )
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    items = client.get("/fabric-catalog/items").json()["items"]
    assert {i["item_id"] for i in items} == {"nb-1", "pl-1", "factorial:employees"}
    fa_item = next(i for i in items if i["item_id"] == "factorial:employees")
    assert fa_item["folder_path"] == ["Factorial"]


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
            "data_owner": ["jose"],
            "data_steward": ["ana"],
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
    assert body["data_owner"] == ["jose"]
    assert body["data_steward"] == ["ana"]
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


def test_update_catalog_item_saves_color_and_icon(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    resp = client.patch(
        "/fabric-catalog/items/nb-1",
        json={**_EMPTY_PAYLOAD, "color": "#3b82f6", "icon": "database"},
    )
    assert resp.status_code == 200
    assert resp.json()["color"] == "#3b82f6"
    assert resp.json()["icon"] == "database"


def test_update_rejects_an_invalid_icon(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    resp = client.patch("/fabric-catalog/items/nb-1", json={**_EMPTY_PAYLOAD, "icon": "not-a-real-icon"})
    assert resp.status_code == 400


def test_update_item_form_save_does_not_wipe_canvas_positions(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    client.put("/fabric-catalog/items/nb-1/canvas-positions", json={"positions": {"pl-1": {"x": 5, "y": 6}}})
    resp = client.patch("/fabric-catalog/items/nb-1", json={**_EMPTY_PAYLOAD, "short_description": "Facturas"})
    assert resp.status_code == 200
    assert resp.json()["canvas_positions"] == {"pl-1": {"x": 5.0, "y": 6.0}}


def test_set_canvas_positions_rejects_a_malformed_position(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    resp = client.put("/fabric-catalog/items/nb-1/canvas-positions", json={"positions": {"pl-1": {"x": "left"}}})
    assert resp.status_code == 422  # pydantic rejects the non-numeric field before it reaches our validation


def test_add_and_remove_relationship_endpoints(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    resp = client.post("/fabric-catalog/items/pl-1/relationships", json={"type": "reads_from", "target_item_id": "nb-1"})
    assert resp.status_code == 200
    assert resp.json()["relationships"] == [{"type": "reads_from", "target_item_id": "nb-1"}]

    resp = client.delete(
        "/fabric-catalog/items/pl-1/relationships",
        params={"type": "reads_from", "target_item_id": "nb-1"},
    )
    assert resp.status_code == 200
    assert resp.json()["relationships"] == []


def test_add_relationship_rejects_an_unknown_type(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    resp = client.post("/fabric-catalog/items/pl-1/relationships", json={"type": "deletes", "target_item_id": "nb-1"})
    assert resp.status_code == 400


def test_reader_cannot_add_a_relationship(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("reader1", "ReaderPass2026!", users_db.ROLE_READER)
    _login(client, "reader1", "ReaderPass2026!")

    resp = client.post("/fabric-catalog/items/pl-1/relationships", json={"type": "reads_from", "target_item_id": "nb-1"})
    assert resp.status_code == 403


_BRONZE_NOTEBOOK_CONTENT = (
    'write_df_to_lakehouse(df_raw, lakehouse_path_tables, "bronze", "bc_customer_list")\n'
)


def test_operator_can_detect_relationships_for_a_table(isolated_state, client, monkeypatch):
    fake = _use_fake_fabric_client(monkeypatch)
    fake.list_items = lambda: [
        {"id": "lh-1", "type": "Lakehouse", "displayName": "Lakehouse"},
        {"id": "nb-bronze", "type": "Notebook", "displayName": "bronze_bc_customer_list"},
    ]
    fake._lakehouse_tables["lh-1"] = [{"schema": "bronze", "table": "bc_customer_list"}]
    fake._model_definitions["nb-bronze"] = [
        {"path": "notebook-content.py", "payload": base64.b64encode(_BRONZE_NOTEBOOK_CONTENT.encode()).decode()}
    ]
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    table_id = "lakehouse-table:lh-1:bronze.bc_customer_list"
    resp = client.get(f"/fabric-catalog/items/{table_id}/detected-relationships")
    assert resp.status_code == 200
    assert resp.json()["candidates"] == [
        {
            "owner_item_id": "nb-bronze",
            "owner_name": "bronze_bc_customer_list",
            "type": "writes_to",
            "target_item_id": table_id,
            "target_name": "bronze.bc_customer_list",
        }
    ]

    # Applying it (via the owner, exactly like the frontend would) makes it
    # disappear from the next detection call -- already saved, not new anymore.
    apply_resp = client.post(
        "/fabric-catalog/items/nb-bronze/relationships", json={"type": "writes_to", "target_item_id": table_id}
    )
    assert apply_resp.status_code == 200
    resp2 = client.get(f"/fabric-catalog/items/{table_id}/detected-relationships")
    assert resp2.json()["candidates"] == []


def test_notebook_scan_cache_status_and_refresh_endpoints(isolated_state, client, monkeypatch):
    fake = _use_fake_fabric_client(monkeypatch)
    fake.list_items = lambda: [
        {"id": "lh-1", "type": "Lakehouse", "displayName": "Lakehouse"},
        {"id": "nb-bronze", "type": "Notebook", "displayName": "bronze_bc_customer_list"},
    ]
    fake._lakehouse_tables["lh-1"] = [{"schema": "bronze", "table": "bc_customer_list"}]
    fake._model_definitions["nb-bronze"] = [
        {"path": "notebook-content.py", "payload": base64.b64encode(_BRONZE_NOTEBOOK_CONTENT.encode()).decode()}
    ]
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    status_resp = client.get("/fabric-catalog/notebook-scan-cache")
    assert status_resp.status_code == 200
    assert status_resp.json() == {"cached": False, "cached_at": ""}

    refresh_resp = client.post("/fabric-catalog/notebook-scan-cache/refresh")
    assert refresh_resp.status_code == 200
    assert refresh_resp.json()["cached"] is True
    assert refresh_resp.json()["cached_at"]

    status_resp2 = client.get("/fabric-catalog/notebook-scan-cache")
    assert status_resp2.json()["cached"] is True

    table_id = "lakehouse-table:lh-1:bronze.bc_customer_list"
    cached_resp = client.get(f"/fabric-catalog/items/{table_id}/detected-relationships", params={"use_cache": "true"})
    assert cached_resp.status_code == 200
    assert cached_resp.json()["candidates"] == [
        {
            "owner_item_id": "nb-bronze",
            "owner_name": "bronze_bc_customer_list",
            "type": "writes_to",
            "target_item_id": table_id,
            "target_name": "bronze.bc_customer_list",
        }
    ]


def test_reader_cannot_refresh_the_notebook_scan_cache(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("reader1", "ReaderPass2026!", users_db.ROLE_READER)
    _login(client, "reader1", "ReaderPass2026!")

    resp = client.post("/fabric-catalog/notebook-scan-cache/refresh")
    assert resp.status_code == 403


def test_detected_relationships_empty_for_an_item_with_nothing_to_detect(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    resp = client.get("/fabric-catalog/items/pl-1/detected-relationships")
    assert resp.status_code == 200
    assert resp.json()["candidates"] == []


def test_reader_cannot_fetch_detected_relationships(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("reader1", "ReaderPass2026!", users_db.ROLE_READER)
    _login(client, "reader1", "ReaderPass2026!")

    resp = client.get("/fabric-catalog/items/pl-1/detected-relationships")
    assert resp.status_code == 403


def test_operator_can_read_a_notebooks_content(isolated_state, client, monkeypatch):
    fake = _use_fake_fabric_client(monkeypatch)
    fake._model_definitions["nb-1"] = [
        {"path": "notebook-content.py", "payload": base64.b64encode(_BRONZE_NOTEBOOK_CONTENT.encode()).decode()}
    ]
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    resp = client.get("/fabric-catalog/items/nb-1/notebook-content")
    assert resp.status_code == 200
    assert resp.json()["content"] == _BRONZE_NOTEBOOK_CONTENT


def test_notebook_content_400s_for_an_item_with_no_notebook_part(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    resp = client.get("/fabric-catalog/items/pl-1/notebook-content")
    assert resp.status_code == 400


def test_reader_cannot_read_a_notebooks_content(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("reader1", "ReaderPass2026!", users_db.ROLE_READER)
    _login(client, "reader1", "ReaderPass2026!")

    resp = client.get("/fabric-catalog/items/nb-1/notebook-content")
    assert resp.status_code == 403


def test_set_favorite_and_hidden_endpoints(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    resp = client.put("/fabric-catalog/items/nb-1/favorite", json={"is_favorite": True})
    assert resp.status_code == 200
    # is_hidden defaults to True (opt-in curation) -- setting favorite alone
    # doesn't touch it.
    assert resp.json() == {"is_favorite": True, "is_hidden": True}

    resp = client.put("/fabric-catalog/items/nb-1/hidden", json={"is_hidden": True})
    assert resp.status_code == 200
    assert resp.json() == {"is_favorite": True, "is_hidden": True}

    listed = client.get("/fabric-catalog/items").json()["items"]
    notebook = next(i for i in listed if i["item_id"] == "nb-1")
    assert notebook["is_favorite"] is True
    assert notebook["is_hidden"] is True


def test_reader_cannot_set_favorite(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("reader1", "ReaderPass2026!", users_db.ROLE_READER)
    _login(client, "reader1", "ReaderPass2026!")

    resp = client.put("/fabric-catalog/items/nb-1/favorite", json={"is_favorite": True})
    assert resp.status_code == 403


def test_operator_can_preview_a_lakehouse_table(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    resp = client.get("/fabric-catalog/items/lakehouse-table:lh-1:bronze.bc_cuentas_contables/preview")
    assert resp.status_code == 200
    assert resp.json() == {"columns": ["id", "name"], "rows": [["1", "Alice"], ["2", "Bob"]]}


def test_preview_rejects_a_non_lakehouse_table_item(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    resp = client.get("/fabric-catalog/items/nb-1/preview")
    assert resp.status_code == 400


def test_reader_cannot_preview_a_table(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("reader1", "ReaderPass2026!", users_db.ROLE_READER)
    _login(client, "reader1", "ReaderPass2026!")

    resp = client.get("/fabric-catalog/items/lakehouse-table:lh-1:bronze.bc_cuentas_contables/preview")
    assert resp.status_code == 403


def test_operator_can_fetch_suggested_columns_for_a_hubspot_table(isolated_state, client, monkeypatch):
    from src.hubspot_client import config as hubspot_config

    _use_fake_fabric_client(monkeypatch)
    monkeypatch.setattr(
        fabric_catalog.table_configs,
        "list_hubspot_tables_full",
        lambda: [{"name": "hubspot_contacts", "object_type": "contacts", "fields": ["email", "hs_object_id"]}],
    )

    class _FakeHubspotClient:
        def __init__(self, settings):
            pass

        def list_properties(self, object_type, include_hidden=False):
            return [
                {"name": "email", "label": "Email", "hidden": False, "calculated": False, "type": "string"},
                {"name": "hs_object_id", "label": "Record ID", "hidden": True, "calculated": False, "type": "number"},
            ]

    monkeypatch.setattr(hubspot_config, "load_settings", lambda: object())
    monkeypatch.setattr("src.hubspot_client.api.HubspotClient", _FakeHubspotClient)

    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    resp = client.get("/fabric-catalog/items/hubspot:hubspot_contacts/suggested-columns")
    assert resp.status_code == 200
    assert resp.json()["columns"] == [
        {"name": "email", "data_type": "string"},
        {"name": "hs_object_id", "data_type": "double"},
    ]


def test_suggested_columns_for_a_lakehouse_table_is_empty(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    resp = client.get("/fabric-catalog/items/nb-1/suggested-columns")
    assert resp.status_code == 200
    assert resp.json()["columns"] == []


def test_reader_cannot_fetch_suggested_columns(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("reader1", "ReaderPass2026!", users_db.ROLE_READER)
    _login(client, "reader1", "ReaderPass2026!")

    resp = client.get("/fabric-catalog/items/nb-1/suggested-columns")
    assert resp.status_code == 403


_VENTAS_ITEM = "lakehouse-table:lh-1:bronze.ventas"


def test_operator_can_read_a_catalog_manifest_seeded_from_the_real_schema(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    resp = client.get(f"/fabric-catalog/items/{_VENTAS_ITEM}/catalog-manifest")
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_manifest"] is False
    assert body["columns"] == [{"name": "id", "data_type": "int", "description": "", "example": ""}]


def test_operator_can_write_and_read_back_a_catalog_manifest(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    payload = {
        "table_description": "Ventas por proyecto",
        "columns": [{"name": "id", "data_type": "int", "description": "Identificador", "example": "123"}],
    }
    put_resp = client.put(f"/fabric-catalog/items/{_VENTAS_ITEM}/catalog-manifest", json=payload)
    assert put_resp.status_code == 200
    assert put_resp.json()["has_manifest"] is True
    assert put_resp.json()["table_description"] == "Ventas por proyecto"

    get_resp = client.get(f"/fabric-catalog/items/{_VENTAS_ITEM}/catalog-manifest")
    assert get_resp.json() == put_resp.json()


def test_set_catalog_manifest_rejects_a_non_lakehouse_item(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    resp = client.put("/fabric-catalog/items/nb-1/catalog-manifest", json={"table_description": "", "columns": [{"name": "x"}]})
    assert resp.status_code == 400


def test_reader_cannot_read_a_catalog_manifest(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("reader1", "ReaderPass2026!", users_db.ROLE_READER)
    _login(client, "reader1", "ReaderPass2026!")

    resp = client.get(f"/fabric-catalog/items/{_VENTAS_ITEM}/catalog-manifest")
    assert resp.status_code == 403


def test_reader_cannot_write_a_catalog_manifest(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("reader1", "ReaderPass2026!", users_db.ROLE_READER)
    _login(client, "reader1", "ReaderPass2026!")

    resp = client.put(f"/fabric-catalog/items/{_VENTAS_ITEM}/catalog-manifest", json={"table_description": "", "columns": [{"name": "x"}]})
    assert resp.status_code == 403


def test_operator_can_read_semantic_model_state_when_not_linked(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    resp = client.get(f"/fabric-catalog/items/{_VENTAS_ITEM}/semantic-model")
    assert resp.status_code == 200
    assert resp.json() == {
        "linked": False,
        "model_item_id": "",
        "model_name": "",
        "columns": [],
        "missing_columns": ["id"],
        "has_real_source": True,
    }


def test_operator_can_create_a_semantic_model(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    resp = client.post(f"/fabric-catalog/items/{_VENTAS_ITEM}/semantic-model", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["linked"] is True
    assert body["has_real_source"] is True
    assert body["model_name"] == "ventas"
    assert [c["name"] for c in body["columns"]] == ["id"]
    assert body["missing_columns"] == []


def test_create_semantic_model_rejects_a_second_one_for_the_same_table(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    client.post(f"/fabric-catalog/items/{_VENTAS_ITEM}/semantic-model", json={})
    resp = client.post(f"/fabric-catalog/items/{_VENTAS_ITEM}/semantic-model", json={})
    assert resp.status_code == 400


def test_operator_can_create_a_manual_semantic_model_for_a_non_lakehouse_item(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    resp = client.post(
        "/fabric-catalog/items/bc:bc_customer/semantic-model",
        json={"item_name": "bc_customer", "columns": [{"name": "email", "data_type": "string"}]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["linked"] is True
    assert body["has_real_source"] is False
    assert body["model_name"] == "bc_customer"
    assert [c["name"] for c in body["columns"]] == ["email"]


def test_create_manual_semantic_model_rejects_an_unknown_data_type(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    resp = client.post(
        "/fabric-catalog/items/bc:bc_customer/semantic-model",
        json={"item_name": "bc_customer", "columns": [{"name": "email", "data_type": "money"}]},
    )
    assert resp.status_code == 400


def test_operator_can_update_semantic_model_descriptions(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    client.post(f"/fabric-catalog/items/{_VENTAS_ITEM}/semantic-model", json={})
    resp = client.patch(
        f"/fabric-catalog/items/{_VENTAS_ITEM}/semantic-model",
        json={"descriptions": {"id": "Identificador de venta."}},
    )
    assert resp.status_code == 200
    columns = {c["name"]: c["description"] for c in resp.json()["columns"]}
    assert columns["id"] == "Identificador de venta."


def test_update_semantic_model_descriptions_without_a_linked_model_is_400(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    resp = client.patch(
        f"/fabric-catalog/items/{_VENTAS_ITEM}/semantic-model", json={"descriptions": {"id": "x"}}
    )
    assert resp.status_code == 400


def test_operator_can_sync_semantic_model_columns(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    client.post(f"/fabric-catalog/items/{_VENTAS_ITEM}/semantic-model", json={})
    resp = client.post(f"/fabric-catalog/items/{_VENTAS_ITEM}/semantic-model/sync-columns")
    assert resp.status_code == 200
    assert resp.json()["missing_columns"] == []


def test_sync_semantic_model_columns_rejects_a_manual_model(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    client.post(
        "/fabric-catalog/items/bc:bc_customer/semantic-model",
        json={"item_name": "bc_customer", "columns": [{"name": "email", "data_type": "string"}]},
    )
    resp = client.post("/fabric-catalog/items/bc:bc_customer/semantic-model/sync-columns")
    assert resp.status_code == 400


def test_operator_can_set_manual_semantic_model_columns(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    client.post(
        "/fabric-catalog/items/bc:bc_customer/semantic-model",
        json={"item_name": "bc_customer", "columns": [{"name": "email", "data_type": "string"}]},
    )
    resp = client.put(
        "/fabric-catalog/items/bc:bc_customer/semantic-model/columns",
        json={"columns": [{"name": "email", "data_type": "string"}, {"name": "activo", "data_type": "boolean"}]},
    )
    assert resp.status_code == 200
    assert [c["name"] for c in resp.json()["columns"]] == ["email", "activo"]


def test_set_manual_semantic_model_columns_rejects_a_lakehouse_table(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    client.post(f"/fabric-catalog/items/{_VENTAS_ITEM}/semantic-model", json={})
    resp = client.put(
        f"/fabric-catalog/items/{_VENTAS_ITEM}/semantic-model/columns",
        json={"columns": [{"name": "x", "data_type": "string"}]},
    )
    assert resp.status_code == 400


def test_reader_cannot_set_manual_semantic_model_columns(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("reader1", "ReaderPass2026!", users_db.ROLE_READER)
    _login(client, "reader1", "ReaderPass2026!")

    resp = client.put(
        "/fabric-catalog/items/bc:bc_customer/semantic-model/columns",
        json={"columns": [{"name": "x", "data_type": "string"}]},
    )
    assert resp.status_code == 403


def test_reader_cannot_create_a_semantic_model(isolated_state, client, monkeypatch):
    _use_fake_fabric_client(monkeypatch)
    make_user("reader1", "ReaderPass2026!", users_db.ROLE_READER)
    _login(client, "reader1", "ReaderPass2026!")

    resp = client.post(f"/fabric-catalog/items/{_VENTAS_ITEM}/semantic-model", json={})
    assert resp.status_code == 403


def test_operator_can_read_type_icons(isolated_state, client):
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    resp = client.get("/fabric-catalog/type-icons")
    assert resp.status_code == 200
    assert resp.json()["icons"]["Lakehouse"] == "database"


def test_admin_can_override_a_type_icon(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")

    resp = client.put("/fabric-catalog/type-icons", json={"type": "Lakehouse", "icon": "boxes"})
    assert resp.status_code == 200
    assert resp.json()["icons"]["Lakehouse"] == "boxes"

    resp2 = client.get("/fabric-catalog/type-icons")
    assert resp2.json()["icons"]["Lakehouse"] == "boxes"


def test_set_type_icon_rejects_an_unknown_icon_key(isolated_state, client):
    make_user("admin2", "AdminPass2026!", users_db.ROLE_ADMIN)
    _login(client, "admin2", "AdminPass2026!")

    resp = client.put("/fabric-catalog/type-icons", json={"type": "Lakehouse", "icon": "not-a-real-icon"})
    assert resp.status_code == 400


def test_operator_cannot_override_a_type_icon(isolated_state, client):
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    resp = client.put("/fabric-catalog/type-icons", json={"type": "Lakehouse", "icon": "boxes"})
    assert resp.status_code == 403


def test_reader_cannot_read_type_icons(isolated_state, client):
    make_user("reader1", "ReaderPass2026!", users_db.ROLE_READER)
    _login(client, "reader1", "ReaderPass2026!")

    resp = client.get("/fabric-catalog/type-icons")
    assert resp.status_code == 403
