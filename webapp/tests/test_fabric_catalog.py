# -*- coding: utf-8 -*-
"""
webapp/fabric_catalog.py -- Fabric structure is always live (via whatever
client is passed in), only the governance metadata (descriptions, owners,
criticality/status, tags, relationships) persists locally.
"""

from __future__ import annotations

import pytest

from webapp import fabric_catalog

_EMPTY_KWARGS = dict(
    short_description="",
    long_description_markdown="",
    owners=[],
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

    def __init__(self, items, folders):
        self._items = items
        self._folders = folders

    def list_items(self):
        return self._items

    def list_folders(self):
        return self._folders


def test_list_catalog_items_merges_live_structure_with_stored_metadata(isolated_state):
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
    _set("nb-1", short_description="Facturas consolidadas", owners=["jose"], criticality="alta")

    items = fabric_catalog.list_catalog_items(client)
    assert len(items) == 2

    notebook = next(i for i in items if i["item_id"] == "nb-1")
    assert notebook["name"] == "silver_facturas"
    assert notebook["type"] == "Notebook"
    assert notebook["folder_path"] == ["ETLs Medallion", "silver"]
    assert notebook["short_description"] == "Facturas consolidadas"
    assert notebook["owners"] == ["jose"]
    assert notebook["criticality"] == "alta"
    assert notebook["reviewed_by"] == ""

    pipeline = next(i for i in items if i["item_id"] == "pl-1")
    assert pipeline["folder_path"] == []  # workspace root -- no folderId at all
    assert pipeline["short_description"] == ""
    assert pipeline["relationships"] == []
    assert pipeline["tags"] == []
    assert pipeline["is_custom"] is False


def test_set_metadata_persists_and_round_trips_all_fields(isolated_state):
    _set(
        "nb-1",
        short_description="Facturas",
        long_description_markdown="# Facturas\nSe construye desde **bronze_facturas.csv**",
        owners=["jose", "ana"],
        criticality="media",
        status="activo",
        tags=["finanzas", "diario"],
        relationships=[{"type": "reads_from", "target_item_id": "lh-bronze"}],
        reviewed_by="admin1",
    )
    stored = fabric_catalog.get_metadata("nb-1")
    assert stored["short_description"] == "Facturas"
    assert stored["long_description_markdown"] == "# Facturas\nSe construye desde **bronze_facturas.csv**"
    assert stored["owners"] == ["jose", "ana"]
    assert stored["criticality"] == "media"
    assert stored["status"] == "activo"
    assert stored["tags"] == ["finanzas", "diario"]
    assert stored["relationships"] == [{"type": "reads_from", "target_item_id": "lh-bronze"}]
    assert stored["reviewed_by"] == "admin1"
    assert stored["reviewed_at"] != ""


def test_set_metadata_dedupes_and_strips_owners_and_tags(isolated_state):
    entry = _set("nb-1", owners=[" jose ", "jose", "ana"], tags=["a", "", " a ", "b"])
    assert entry["owners"] == ["jose", "ana"]
    assert entry["tags"] == ["a", "b"]


def test_get_metadata_for_unknown_item_returns_fully_shaped_empty_entry(isolated_state):
    assert fabric_catalog.get_metadata("does-not-exist") == {
        "short_description": "",
        "long_description_markdown": "",
        "owners": [],
        "criticality": "",
        "status": "",
        "tags": [],
        "relationships": [],
        "reviewed_by": "",
        "reviewed_at": "",
        "is_custom": False,
        "name": "",
        "type": "",
    }


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


def test_create_custom_item_persists_and_appears_in_the_listing(isolated_state):
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
    Fabric item's metadata (even without is_custom set) must go through
    delete_metadata(), never silently vanish via this path."""
    _set("nb-1", short_description="algo")
    with pytest.raises(ValueError):
        fabric_catalog.delete_custom_item("nb-1")
    assert fabric_catalog.get_metadata("nb-1")["short_description"] == "algo"


def test_folder_path_handles_a_deeply_nested_folder(isolated_state):
    client = _FakeFabricClient(
        items=[{"id": "nb-1", "type": "Notebook", "displayName": "x", "folderId": "f3"}],
        folders=[
            {"id": "f1", "displayName": "Sandbox"},
            {"id": "f2", "displayName": "EDA", "parentFolderId": "f1"},
            {"id": "f3", "displayName": "sub", "parentFolderId": "f2"},
        ],
    )
    items = fabric_catalog.list_catalog_items(client)
    assert items[0]["folder_path"] == ["Sandbox", "EDA", "sub"]


def test_folder_path_does_not_infinite_loop_on_a_cyclic_parent_reference(isolated_state):
    """Fabric shouldn't ever produce this, but a defensive guard here is
    cheap and turns a hypothetical bad response into a truncated path
    instead of a hung request."""
    client = _FakeFabricClient(
        items=[{"id": "nb-1", "type": "Notebook", "displayName": "x", "folderId": "f1"}],
        folders=[
            {"id": "f1", "displayName": "A", "parentFolderId": "f2"},
            {"id": "f2", "displayName": "B", "parentFolderId": "f1"},
        ],
    )
    items = fabric_catalog.list_catalog_items(client)
    assert items[0]["folder_path"] == ["B", "A"]
