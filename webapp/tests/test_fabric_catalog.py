# -*- coding: utf-8 -*-
"""
webapp/fabric_catalog.py -- Fabric/BC/HubSpot structure is always live/static
config (never cached here for Fabric, read fresh from tables.yaml/
hubspot_tables.yaml for the other two), only the governance metadata
(descriptions, roles, criticality/status, tags, relationships, ...)
persists locally.
"""

from __future__ import annotations

import pytest

from webapp import fabric_catalog

_EMPTY_KWARGS = dict(
    short_description="",
    long_description_markdown="",
    data_owner=[],
    data_steward=[],
    data_custodian=[],
    data_consumer=[],
    criticality="",
    status="",
    tags=[],
    relationships=[],
    reviewed_by="",
)


def _set(item_id: str, **overrides):
    kwargs = {**_EMPTY_KWARGS, **overrides}
    return fabric_catalog.set_metadata(item_id, **kwargs)


class _FakeFabricClient:
    """Mirrors the real Fabric Items/Folders API's shape (id/type/
    displayName/folderId for items, id/displayName/parentFolderId for
    folders) -- reproduced live against the real workspace before writing
    this module, see FabricPipelineClient.list_items()/list_folders()."""

    def __init__(self, items, folders, lakehouse_tables=None, lakehouse_columns=None):
        self._items = items
        self._folders = folders
        # {lakehouse_item_id: [{"schema": ..., "table": ...}, ...]}
        self._lakehouse_tables = lakehouse_tables or {}
        # {(lakehouse_item_id, schema, table): [{"name": ..., "sql_type": ...}, ...]}
        self._lakehouse_columns = lakehouse_columns or {}
        # {model_item_id: [part, ...]} -- created via create_item(), the
        # same shape get_definition()'s real response nests under "parts".
        self._model_definitions: dict = {}
        self._next_id = 1
        self.workspace_id = "ws-fake"

    def list_items(self):
        return self._items

    def list_folders(self):
        return self._folders

    def list_lakehouse_tables(self, item_id, display_name):
        return self._lakehouse_tables.get(item_id, [])

    def list_lakehouse_table_columns(self, item_id, display_name, schema, table):
        return self._lakehouse_columns.get((item_id, schema, table), [])

    def get_item(self, item_id):
        from src.fabric_pipelines.api import FabricPipelineError

        found = next((i for i in self._items if i["id"] == item_id), None)
        if found is None:
            raise FabricPipelineError(f"item not found: {item_id}")
        return found

    def preview_lakehouse_table(self, item_id, display_name, schema, table, limit=10):
        return {
            "columns": ["id", "name"],
            "rows": [["1", "a"]],
            "_called_with": (item_id, display_name, schema, table, limit),
        }

    def create_item(self, display_name, item_type, parts):
        item_id = f"model-{self._next_id}"
        self._next_id += 1
        self._model_definitions[item_id] = parts
        self._items.append({"id": item_id, "type": item_type, "displayName": display_name})
        return item_id

    def get_definition(self, item_id):
        return {"definition": {"parts": self._model_definitions[item_id]}}

    def update_item_definition(self, item_id, parts):
        self._model_definitions[item_id] = parts


_EMPTY_CLIENT = _FakeFabricClient(items=[], folders=[])


def _no_bc_or_hubspot_tables(monkeypatch):
    """Most tests only care about Fabric/custom items -- silence the
    other three sources so list_catalog_items() output stays predictable
    without every test needing to know about
    tables.yaml/hubspot_tables.yaml/factorial_tables.yaml."""
    monkeypatch.setattr(fabric_catalog.table_configs, "list_factorial_tables_full", lambda: [])
    monkeypatch.setattr(fabric_catalog.table_configs, "list_bc_tables_full", lambda: [])
    monkeypatch.setattr(fabric_catalog.table_configs, "list_hubspot_tables_full", lambda: [])


def test_list_catalog_items_merges_live_structure_with_stored_metadata(isolated_state, monkeypatch):
    _no_bc_or_hubspot_tables(monkeypatch)
    client = _FakeFabricClient(
        items=[
            {"id": "nb-1", "type": "Notebook", "displayName": "silver_facturas", "folderId": "f-silver"},
            {"id": "pl-1", "type": "DataPipeline", "displayName": "Pipeline_CADE_Bronce"},
        ],
        folders=[
            {"id": "f-root", "displayName": "ETLs Medallion"},
            {"id": "f-silver", "displayName": "silver", "parentFolderId": "f-root"},
        ],
    )
    _set("nb-1", short_description="Facturas consolidadas", data_owner=["jose"], criticality="alta")

    items = fabric_catalog.list_catalog_items(client)
    assert len(items) == 2

    notebook = next(i for i in items if i["item_id"] == "nb-1")
    assert notebook["name"] == "silver_facturas"
    assert notebook["type"] == "Notebook"
    assert notebook["folder_path"] == ["Fabric", "ETLs Medallion", "silver"]
    assert notebook["short_description"] == "Facturas consolidadas"
    assert notebook["data_owner"] == ["jose"]
    assert notebook["criticality"] == "alta"
    assert notebook["reviewed_by"] == ""

    pipeline = next(i for i in items if i["item_id"] == "pl-1")
    assert pipeline["folder_path"] == ["Fabric"]  # workspace root -- no folderId at all
    assert pipeline["short_description"] == ""
    assert pipeline["relationships"] == []
    assert pipeline["tags"] == []
    assert pipeline["is_custom"] is False
    assert pipeline["color"] == ""
    assert pipeline["icon"] == ""
    assert pipeline["canvas_positions"] == {}
    assert pipeline["is_favorite"] is False
    assert pipeline["is_hidden"] is True  # opt-in curation: everything starts hidden


def test_list_catalog_items_merges_bc_and_hubspot_static_tables(isolated_state, monkeypatch):
    monkeypatch.setattr(fabric_catalog.table_configs, "list_factorial_tables_full", lambda: [])
    monkeypatch.setattr(
        fabric_catalog.table_configs,
        "list_bc_tables_full",
        lambda: [{"name": "bc_customer", "description": "Customer API", "url": "...", "incremental": True}],
    )
    monkeypatch.setattr(
        fabric_catalog.table_configs,
        "list_hubspot_tables_full",
        lambda: [{"name": "hubspot_contacts", "description": "HubSpot contacts", "object_type": "contacts"}],
    )
    items = fabric_catalog.list_catalog_items(_EMPTY_CLIENT)
    assert len(items) == 2

    bc_item = next(i for i in items if i["item_id"] == "bc:bc_customer")
    assert bc_item["name"] == "bc_customer"
    assert bc_item["folder_path"] == ["Business Central"]
    assert bc_item["is_custom"] is False

    hs_item = next(i for i in items if i["item_id"] == "hubspot:hubspot_contacts")
    assert hs_item["name"] == "hubspot_contacts"
    assert hs_item["folder_path"] == ["HubSpot"]


def test_list_catalog_items_merges_factorial_static_tables(isolated_state, monkeypatch):
    monkeypatch.setattr(fabric_catalog.table_configs, "list_bc_tables_full", lambda: [])
    monkeypatch.setattr(fabric_catalog.table_configs, "list_hubspot_tables_full", lambda: [])
    monkeypatch.setattr(
        fabric_catalog.table_configs,
        "list_factorial_tables_full",
        lambda: [{"name": "employees", "description": "Empleados", "path": "/employees"}],
    )
    items = fabric_catalog.list_catalog_items(_EMPTY_CLIENT)
    assert len(items) == 1

    fa_item = next(i for i in items if i["item_id"] == "factorial:employees")
    assert fa_item["name"] == "employees"
    assert fa_item["type"] == "Tabla"
    assert fa_item["folder_path"] == ["Factorial"]
    assert fa_item["is_custom"] is False


def test_list_catalog_items_factorial_table_keeps_its_saved_metadata(isolated_state, monkeypatch):
    monkeypatch.setattr(fabric_catalog.table_configs, "list_bc_tables_full", lambda: [])
    monkeypatch.setattr(fabric_catalog.table_configs, "list_hubspot_tables_full", lambda: [])
    monkeypatch.setattr(
        fabric_catalog.table_configs, "list_factorial_tables_full", lambda: [{"name": "employees"}]
    )
    _set("factorial:employees", short_description="Plantilla de la empresa", data_owner=["rrhh"])

    items = fabric_catalog.list_catalog_items(_EMPTY_CLIENT)
    fa_item = next(i for i in items if i["item_id"] == "factorial:employees")
    assert fa_item["short_description"] == "Plantilla de la empresa"
    assert fa_item["data_owner"] == ["rrhh"]


def test_list_catalog_items_merges_lakehouse_tables_nested_under_the_lakehouse(isolated_state, monkeypatch):
    _no_bc_or_hubspot_tables(monkeypatch)
    client = _FakeFabricClient(
        items=[{"id": "lh-1", "type": "Lakehouse", "displayName": "Lakehouse", "folderId": "f-root"}],
        folders=[{"id": "f-root", "displayName": "Sandbox"}],
        lakehouse_tables={"lh-1": [{"schema": "bronze", "table": "bc_cuentas_contables"}]},
    )
    items = fabric_catalog.list_catalog_items(client)
    assert len(items) == 2

    lakehouse = next(i for i in items if i["item_id"] == "lh-1")
    assert lakehouse["folder_path"] == ["Fabric", "Sandbox"]

    table_id = "lakehouse-table:lh-1:bronze.bc_cuentas_contables"
    table = next(i for i in items if i["item_id"] == table_id)
    assert table["name"] == "bronze.bc_cuentas_contables"
    assert table["type"] == "Tabla"
    # One level deeper than the Lakehouse itself -- reads as "inside" it.
    assert table["folder_path"] == ["Fabric", "Sandbox", "Lakehouse"]
    assert table["is_custom"] is False


def test_list_catalog_items_only_queries_lakehouse_tables_for_lakehouse_items(isolated_state, monkeypatch):
    """A Notebook/DataPipeline/etc. never triggers the SQL-endpoint lookup --
    only an item whose type is literally "Lakehouse" does."""
    _no_bc_or_hubspot_tables(monkeypatch)

    class _ExplodingLakehouseTables(_FakeFabricClient):
        def list_lakehouse_tables(self, item_id, display_name):
            raise AssertionError("list_lakehouse_tables should not be called for a non-Lakehouse item")

    client = _ExplodingLakehouseTables(
        items=[{"id": "nb-1", "type": "Notebook", "displayName": "silver_facturas"}],
        folders=[],
    )
    items = fabric_catalog.list_catalog_items(client)
    assert len(items) == 1


def test_list_catalog_items_lakehouse_table_keeps_its_saved_metadata(isolated_state, monkeypatch):
    _no_bc_or_hubspot_tables(monkeypatch)
    table_id = "lakehouse-table:lh-1:bronze.bc_cuentas_contables"
    _set(table_id, short_description="Cuentas contables de BC", data_owner=["ana"])

    client = _FakeFabricClient(
        items=[{"id": "lh-1", "type": "Lakehouse", "displayName": "Lakehouse"}],
        folders=[],
        lakehouse_tables={"lh-1": [{"schema": "bronze", "table": "bc_cuentas_contables"}]},
    )
    items = fabric_catalog.list_catalog_items(client)
    table = next(i for i in items if i["item_id"] == table_id)
    assert table["short_description"] == "Cuentas contables de BC"
    assert table["data_owner"] == ["ana"]


def test_parse_lakehouse_table_id_round_trips():
    parsed = fabric_catalog.parse_lakehouse_table_id("lakehouse-table:lh-1:bronze.bc_cuentas_contables")
    assert parsed == ("lh-1", "bronze", "bc_cuentas_contables")


@pytest.mark.parametrize("item_id", ["bc:bc_customer", "hubspot:hubspot_contacts", "custom:abc", "nb-1", ""])
def test_parse_lakehouse_table_id_returns_none_for_anything_else(item_id):
    assert fabric_catalog.parse_lakehouse_table_id(item_id) is None


def test_preview_lakehouse_table_rejects_a_non_lakehouse_table_id(isolated_state):
    with pytest.raises(ValueError, match="previsualizable"):
        fabric_catalog.preview_lakehouse_table(_EMPTY_CLIENT, "bc:bc_customer")


def test_preview_lakehouse_table_looks_up_the_lakehouses_display_name_and_delegates(isolated_state):
    client = _FakeFabricClient(
        items=[{"id": "lh-1", "type": "Lakehouse", "displayName": "Lakehouse"}],
        folders=[],
    )
    result = fabric_catalog.preview_lakehouse_table(client, "lakehouse-table:lh-1:bronze.bc_cuentas_contables")
    assert result["columns"] == ["id", "name"]
    assert result["_called_with"] == ("lh-1", "Lakehouse", "bronze", "bc_cuentas_contables", 10)


# --------------------------------------------------------------------------------------
# Semantic models
# --------------------------------------------------------------------------------------

_LH_ITEM = {"id": "lh-1", "type": "Lakehouse", "displayName": "Lakehouse"}
_TABLE_ITEM_ID = "lakehouse-table:lh-1:bronze.ventas"
_SOURCE_COLUMNS = [{"name": "id", "sql_type": "int"}, {"name": "importe", "sql_type": "decimal"}]


def _client_with_source_table(columns=None):
    return _FakeFabricClient(
        items=[dict(_LH_ITEM)],
        folders=[],
        lakehouse_columns={("lh-1", "bronze", "ventas"): columns if columns is not None else list(_SOURCE_COLUMNS)},
    )


def test_get_semantic_model_state_rejects_a_non_lakehouse_table_id(isolated_state):
    with pytest.raises(ValueError, match="no es una tabla de Lakehouse"):
        fabric_catalog.get_semantic_model_state(_EMPTY_CLIENT, "bc:bc_customer")


def test_get_semantic_model_state_not_linked_lists_every_source_column_as_missing(isolated_state):
    client = _client_with_source_table()
    state = fabric_catalog.get_semantic_model_state(client, _TABLE_ITEM_ID)
    assert state == {
        "linked": False,
        "model_item_id": "",
        "model_name": "",
        "columns": [],
        "missing_columns": ["id", "importe"],
    }


def test_create_semantic_model_auto_detects_columns_and_links_it(isolated_state):
    client = _client_with_source_table()
    state = fabric_catalog.create_semantic_model(client, _TABLE_ITEM_ID)

    assert state["linked"] is True
    assert state["model_name"] == "ventas"
    assert [c["name"] for c in state["columns"]] == ["id", "importe"]
    assert all(c["description"] == "" for c in state["columns"])
    assert state["missing_columns"] == []

    # Persisted onto the catalog item, so a later call resolves the same model.
    assert fabric_catalog.get_metadata(_TABLE_ITEM_ID)["semantic_model_item_id"] == state["model_item_id"]


def test_create_semantic_model_rejects_a_table_that_already_has_one(isolated_state):
    client = _client_with_source_table()
    fabric_catalog.create_semantic_model(client, _TABLE_ITEM_ID)
    with pytest.raises(ValueError, match="ya tiene un modelo semántico"):
        fabric_catalog.create_semantic_model(client, _TABLE_ITEM_ID)


def test_create_semantic_model_rejects_a_table_with_no_detectable_columns(isolated_state):
    client = _client_with_source_table(columns=[])
    with pytest.raises(ValueError, match="No se encontraron columnas"):
        fabric_catalog.create_semantic_model(client, _TABLE_ITEM_ID)


def test_get_semantic_model_state_reads_back_the_created_model(isolated_state):
    client = _client_with_source_table()
    created = fabric_catalog.create_semantic_model(client, _TABLE_ITEM_ID)
    state = fabric_catalog.get_semantic_model_state(client, _TABLE_ITEM_ID)
    assert state == created


def test_get_semantic_model_state_self_heals_when_the_linked_model_was_deleted_in_fabric(isolated_state):
    client = _client_with_source_table()
    fabric_catalog.create_semantic_model(client, _TABLE_ITEM_ID)
    # Simulate the model having been deleted directly in Fabric.
    client._items = [i for i in client._items if i["type"] != "SemanticModel"]

    state = fabric_catalog.get_semantic_model_state(client, _TABLE_ITEM_ID)
    assert state["linked"] is False
    assert fabric_catalog.get_metadata(_TABLE_ITEM_ID)["semantic_model_item_id"] == ""


def test_update_semantic_model_descriptions_requires_a_linked_model(isolated_state):
    client = _client_with_source_table()
    with pytest.raises(ValueError, match="todavía no tiene"):
        fabric_catalog.update_semantic_model_descriptions(client, _TABLE_ITEM_ID, {"id": "x"})


def test_update_semantic_model_descriptions_saves_and_leaves_other_columns_alone(isolated_state):
    client = _client_with_source_table()
    fabric_catalog.create_semantic_model(client, _TABLE_ITEM_ID)

    state = fabric_catalog.update_semantic_model_descriptions(
        client, _TABLE_ITEM_ID, {"importe": "Importe en euros."}
    )
    by_name = {c["name"]: c["description"] for c in state["columns"]}
    assert by_name["importe"] == "Importe en euros."
    assert by_name["id"] == ""


def test_sync_semantic_model_columns_requires_a_linked_model(isolated_state):
    client = _client_with_source_table()
    with pytest.raises(ValueError, match="todavía no tiene"):
        fabric_catalog.sync_semantic_model_columns(client, _TABLE_ITEM_ID)


def test_sync_semantic_model_columns_adds_a_column_added_to_the_source_after_creation(isolated_state):
    client = _client_with_source_table(columns=[{"name": "id", "sql_type": "int"}])
    fabric_catalog.create_semantic_model(client, _TABLE_ITEM_ID)

    # Schema drift: the real table now also has "importe".
    client._lakehouse_columns[("lh-1", "bronze", "ventas")] = list(_SOURCE_COLUMNS)

    state = fabric_catalog.sync_semantic_model_columns(client, _TABLE_ITEM_ID)
    assert [c["name"] for c in state["columns"]] == ["id", "importe"]
    assert state["missing_columns"] == []


def test_sync_semantic_model_columns_is_a_no_op_when_nothing_is_missing(isolated_state):
    client = _client_with_source_table()
    created = fabric_catalog.create_semantic_model(client, _TABLE_ITEM_ID)
    synced = fabric_catalog.sync_semantic_model_columns(client, _TABLE_ITEM_ID)
    assert synced == created


def test_list_catalog_items_bc_table_keeps_its_saved_metadata(isolated_state, monkeypatch):
    monkeypatch.setattr(
        fabric_catalog.table_configs,
        "list_bc_tables_full",
        lambda: [{"name": "bc_customer"}],
    )
    monkeypatch.setattr(fabric_catalog.table_configs, "list_hubspot_tables_full", lambda: [])
    monkeypatch.setattr(fabric_catalog.table_configs, "list_factorial_tables_full", lambda: [])
    _set("bc:bc_customer", short_description="Clientes de BC", data_steward=["ana"])

    items = fabric_catalog.list_catalog_items(_EMPTY_CLIENT)
    bc_item = next(i for i in items if i["item_id"] == "bc:bc_customer")
    assert bc_item["short_description"] == "Clientes de BC"
    assert bc_item["data_steward"] == ["ana"]


def test_set_metadata_persists_and_round_trips_all_fields(isolated_state):
    _set(
        "nb-1",
        short_description="Facturas",
        long_description_markdown="# Facturas\nSe construye desde **bronze_facturas.csv**",
        data_owner=["jose"],
        data_steward=["ana"],
        data_custodian=["it-team"],
        data_consumer=["comercial"],
        criticality="media",
        status="activo",
        tags=["finanzas", "diario"],
        relationships=[{"type": "reads_from", "target_item_id": "lh-bronze"}],
        reviewed_by="admin1",
    )
    stored = fabric_catalog.get_metadata("nb-1")
    assert stored["short_description"] == "Facturas"
    assert stored["long_description_markdown"] == "# Facturas\nSe construye desde **bronze_facturas.csv**"
    assert stored["data_owner"] == ["jose"]
    assert stored["data_steward"] == ["ana"]
    assert stored["data_custodian"] == ["it-team"]
    assert stored["data_consumer"] == ["comercial"]
    assert stored["criticality"] == "media"
    assert stored["status"] == "activo"
    assert stored["tags"] == ["finanzas", "diario"]
    assert stored["relationships"] == [{"type": "reads_from", "target_item_id": "lh-bronze"}]
    assert stored["reviewed_by"] == "admin1"
    assert stored["reviewed_at"] != ""


def test_set_metadata_dedupes_and_strips_role_lists_and_tags(isolated_state):
    entry = _set("nb-1", data_owner=[" jose ", "jose", "ana"], tags=["a", "", " a ", "b"])
    assert entry["data_owner"] == ["jose", "ana"]
    assert entry["tags"] == ["a", "b"]


def test_get_metadata_for_unknown_item_returns_fully_shaped_empty_entry(isolated_state):
    assert fabric_catalog.get_metadata("does-not-exist") == {
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
        "reviewed_by": "",
        "reviewed_at": "",
        "is_custom": False,
        "name": "",
        "type": "",
        "color": "",
        "icon": "",
        "canvas_positions": {},
        "is_favorite": False,
        "is_hidden": True,  # opt-in curation: everything starts hidden
        "semantic_model_item_id": "",
    }


def test_set_metadata_persists_color_and_icon(isolated_state):
    entry = _set("nb-1", color="#3b82f6", icon="database")
    assert entry["color"] == "#3b82f6"
    assert entry["icon"] == "database"


def test_set_metadata_rejects_a_non_hex_color(isolated_state):
    with pytest.raises(ValueError, match="[Cc]olor"):
        _set("nb-1", color="blue")


def test_set_metadata_rejects_an_unknown_icon(isolated_state):
    with pytest.raises(ValueError, match="[Ii]cono"):
        _set("nb-1", icon="not-a-real-icon")


def test_set_metadata_persists_canvas_positions(isolated_state):
    entry = _set("nb-1", canvas_positions={"pl-1": {"x": 10, "y": 20.5}})
    assert entry["canvas_positions"] == {"pl-1": {"x": 10, "y": 20.5}}


def test_set_metadata_rejects_a_malformed_canvas_position(isolated_state):
    with pytest.raises(ValueError):
        _set("nb-1", canvas_positions={"pl-1": {"x": 10}})


def test_set_metadata_rejects_a_non_numeric_canvas_position(isolated_state):
    with pytest.raises(ValueError):
        _set("nb-1", canvas_positions={"pl-1": {"x": "left", "y": 20}})


def test_set_canvas_positions_only_touches_positions(isolated_state):
    _set("nb-1", short_description="Facturas", color="#3b82f6")
    entry = fabric_catalog.set_canvas_positions("nb-1", {"pl-1": {"x": 5, "y": 6}})
    assert entry["canvas_positions"] == {"pl-1": {"x": 5, "y": 6}}
    assert entry["short_description"] == "Facturas"
    assert entry["color"] == "#3b82f6"


def test_update_item_form_save_does_not_wipe_canvas_positions(isolated_state):
    """The general edit form (PATCH /items/{id}) never sends canvas
    positions -- set_metadata() must preserve the existing ones when the
    caller omits the argument, not silently clear the canvas."""
    fabric_catalog.set_canvas_positions("nb-1", {"pl-1": {"x": 5, "y": 6}})
    _set("nb-1", short_description="Facturas")
    assert fabric_catalog.get_metadata("nb-1")["canvas_positions"] == {"pl-1": {"x": 5, "y": 6}}


def test_set_favorite_and_hidden_do_not_touch_other_fields_or_stamp_reviewed(isolated_state):
    _set("nb-1", short_description="Facturas", reviewed_by="admin1")
    entry = fabric_catalog.set_favorite("nb-1", True)
    assert entry["is_favorite"] is True
    assert entry["short_description"] == "Facturas"
    assert entry["reviewed_by"] == "admin1"  # unchanged -- bookmarking isn't a review

    entry = fabric_catalog.set_hidden("nb-1", True)
    assert entry["is_hidden"] is True
    assert entry["is_favorite"] is True  # the earlier flag survives too
    assert entry["short_description"] == "Facturas"


def test_update_item_form_save_does_not_wipe_favorite_or_hidden_flags(isolated_state):
    fabric_catalog.set_favorite("nb-1", True)
    fabric_catalog.set_hidden("nb-1", True)
    _set("nb-1", short_description="Facturas")
    stored = fabric_catalog.get_metadata("nb-1")
    assert stored["is_favorite"] is True
    assert stored["is_hidden"] is True


def test_new_items_default_to_hidden(isolated_state, monkeypatch):
    """Opt-in curation: with Fabric+BC+HubSpot merged an untouched catalog
    is 100+ items, so nothing shows until someone explicitly un-hides it."""
    _no_bc_or_hubspot_tables(monkeypatch)
    client = _FakeFabricClient(items=[{"id": "nb-1", "type": "Notebook", "displayName": "x"}], folders=[])
    items = fabric_catalog.list_catalog_items(client)
    assert items[0]["is_hidden"] is True


def test_set_hidden_can_unhide_and_it_survives_a_form_save(isolated_state):
    fabric_catalog.set_hidden("nb-1", False)
    _set("nb-1", short_description="Facturas")
    assert fabric_catalog.get_metadata("nb-1")["is_hidden"] is False


def test_add_relationship_appends_without_touching_other_fields(isolated_state):
    _set("nb-1", short_description="Facturas", data_owner=["jose"])
    entry = fabric_catalog.add_relationship("nb-1", "reads_from", "lh-bronze", reviewed_by="admin1")
    assert entry["relationships"] == [{"type": "reads_from", "target_item_id": "lh-bronze"}]
    assert entry["short_description"] == "Facturas"
    assert entry["data_owner"] == ["jose"]
    assert entry["reviewed_by"] == "admin1"


def test_remove_relationship_removes_only_the_matching_one(isolated_state):
    _set(
        "nb-1",
        relationships=[
            {"type": "reads_from", "target_item_id": "lh-bronze"},
            {"type": "writes_to", "target_item_id": "lh-gold"},
        ],
    )
    entry = fabric_catalog.remove_relationship("nb-1", "reads_from", "lh-bronze", reviewed_by="admin1")
    assert entry["relationships"] == [{"type": "writes_to", "target_item_id": "lh-gold"}]


def test_set_metadata_preserves_a_custom_items_identity(isolated_state):
    """A regression guard: set_metadata() (the general edit-form save) must
    not silently strip is_custom/name/type when saving a custom item's
    other fields -- that would make it vanish from list_catalog_items()
    entirely (it's neither a live source item nor recognized as custom)."""
    created = fabric_catalog.create_custom_item("Excel de ventas", "Fuente externa", created_by="admin1")
    item_id = created["item_id"]
    _set(item_id, short_description="Datos de ventas mensuales", reviewed_by="admin2")
    stored = fabric_catalog.get_metadata(item_id)
    assert stored["is_custom"] is True
    assert stored["name"] == "Excel de ventas"
    assert stored["type"] == "Fuente externa"
    assert stored["short_description"] == "Datos de ventas mensuales"


def test_add_relationship_accepts_generates_and_updates(isolated_state):
    entry = fabric_catalog.add_relationship("nb-1", "generates", "lh-gold", reviewed_by="admin1")
    entry = fabric_catalog.add_relationship("nb-1", "updates", "lh-silver", reviewed_by="admin1")
    assert entry["relationships"] == [
        {"type": "generates", "target_item_id": "lh-gold"},
        {"type": "updates", "target_item_id": "lh-silver"},
    ]


def test_set_metadata_rejects_an_unknown_relationship_type(isolated_state):
    with pytest.raises(ValueError, match="relación"):
        _set("nb-1", relationships=[{"type": "deletes", "target_item_id": "x"}])


def test_set_metadata_rejects_a_relationship_missing_a_target(isolated_state):
    with pytest.raises(ValueError):
        _set("nb-1", relationships=[{"type": "reads_from", "target_item_id": ""}])


def test_set_metadata_rejects_self_referencing_relationship(isolated_state):
    with pytest.raises(ValueError, match="sí mismo|consigo"):
        _set("nb-1", relationships=[{"type": "writes_to", "target_item_id": "nb-1"}])


def test_set_metadata_rejects_an_unknown_criticality(isolated_state):
    with pytest.raises(ValueError, match="[Cc]riticidad"):
        _set("nb-1", criticality="urgentisimo")


def test_set_metadata_rejects_an_unknown_status(isolated_state):
    with pytest.raises(ValueError, match="[Ee]stado"):
        _set("nb-1", status="no_existe")


def test_create_custom_item_persists_and_appears_in_the_listing(isolated_state, monkeypatch):
    _no_bc_or_hubspot_tables(monkeypatch)
    client = _FakeFabricClient(
        items=[{"id": "nb-1", "type": "Notebook", "displayName": "silver_facturas"}],
        folders=[],
    )
    created = fabric_catalog.create_custom_item("Excel de ventas", "Fuente externa", created_by="admin1")
    assert created["item_id"].startswith(fabric_catalog.CUSTOM_ID_PREFIX)
    assert created["name"] == "Excel de ventas"
    assert created["type"] == "Fuente externa"
    assert created["folder_path"] == ["Personalizados"]
    assert created["is_custom"] is True
    assert created["reviewed_by"] == "admin1"

    items = fabric_catalog.list_catalog_items(client)
    assert len(items) == 2
    custom = next(i for i in items if i["is_custom"])
    assert custom["item_id"] == created["item_id"]
    assert custom["name"] == "Excel de ventas"
    assert custom["folder_path"] == ["Personalizados"]


def test_create_custom_item_defaults_type_when_blank(isolated_state):
    created = fabric_catalog.create_custom_item("Proceso manual", "  ", created_by="admin1")
    assert created["type"] == "Personalizado"


def test_create_custom_item_rejects_a_blank_name(isolated_state):
    with pytest.raises(ValueError):
        fabric_catalog.create_custom_item("   ", "algo", created_by="admin1")


def test_delete_custom_item_removes_it(isolated_state):
    created = fabric_catalog.create_custom_item("Excel de ventas", "Fuente externa", created_by="admin1")
    fabric_catalog.delete_custom_item(created["item_id"])
    assert fabric_catalog.get_metadata(created["item_id"])["name"] == ""


def test_delete_custom_item_rejects_an_unknown_id(isolated_state):
    with pytest.raises(ValueError):
        fabric_catalog.delete_custom_item("custom:does-not-exist")


def test_delete_custom_item_refuses_to_delete_a_real_items_metadata(isolated_state):
    """delete_custom_item is only for entries this module invented -- a real
    item's metadata (even without is_custom set) must go through
    delete_metadata(), never silently vanish via this path."""
    _set("nb-1", short_description="algo")
    with pytest.raises(ValueError):
        fabric_catalog.delete_custom_item("nb-1")
    assert fabric_catalog.get_metadata("nb-1")["short_description"] == "algo"


def test_folder_path_handles_a_deeply_nested_folder(isolated_state, monkeypatch):
    _no_bc_or_hubspot_tables(monkeypatch)
    client = _FakeFabricClient(
        items=[{"id": "nb-1", "type": "Notebook", "displayName": "x", "folderId": "f3"}],
        folders=[
            {"id": "f1", "displayName": "Sandbox"},
            {"id": "f2", "displayName": "EDA", "parentFolderId": "f1"},
            {"id": "f3", "displayName": "sub", "parentFolderId": "f2"},
        ],
    )
    items = fabric_catalog.list_catalog_items(client)
    assert items[0]["folder_path"] == ["Fabric", "Sandbox", "EDA", "sub"]


def test_folder_path_does_not_infinite_loop_on_a_cyclic_parent_reference(isolated_state, monkeypatch):
    """Fabric shouldn't ever produce this, but a defensive guard here is
    cheap and turns a hypothetical bad response into a truncated path
    instead of a hung request."""
    _no_bc_or_hubspot_tables(monkeypatch)
    client = _FakeFabricClient(
        items=[{"id": "nb-1", "type": "Notebook", "displayName": "x", "folderId": "f1"}],
        folders=[
            {"id": "f1", "displayName": "A", "parentFolderId": "f2"},
            {"id": "f2", "displayName": "B", "parentFolderId": "f1"},
        ],
    )
    items = fabric_catalog.list_catalog_items(client)
    assert items[0]["folder_path"] == ["Fabric", "B", "A"]
