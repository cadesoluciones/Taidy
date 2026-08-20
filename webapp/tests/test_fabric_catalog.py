# -*- coding: utf-8 -*-
"""
webapp/fabric_catalog.py -- Fabric structure is always live (via whatever
client is passed in), only description/relationships persist locally.
"""

from __future__ import annotations

import pytest

from webapp import fabric_catalog


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
    fabric_catalog.set_metadata("nb-1", description="Facturas consolidadas", relationships=[])

    items = fabric_catalog.list_catalog_items(client)
    assert len(items) == 2

    notebook = next(i for i in items if i["item_id"] == "nb-1")
    assert notebook["name"] == "silver_facturas"
    assert notebook["type"] == "Notebook"
    assert notebook["folder_path"] == ["ETLs Medallion", "silver"]
    assert notebook["description"] == "Facturas consolidadas"

    pipeline = next(i for i in items if i["item_id"] == "pl-1")
    assert pipeline["folder_path"] == []  # workspace root -- no folderId at all
    assert pipeline["description"] == ""
    assert pipeline["relationships"] == []


def test_set_metadata_persists_and_round_trips_relationships(isolated_state):
    fabric_catalog.set_metadata(
        "nb-1",
        description="Se construye desde bronze_facturas.csv",
        relationships=[{"type": "reads_from", "target_item_id": "lh-bronze"}],
    )
    stored = fabric_catalog.get_metadata("nb-1")
    assert stored["description"] == "Se construye desde bronze_facturas.csv"
    assert stored["relationships"] == [{"type": "reads_from", "target_item_id": "lh-bronze"}]


def test_get_metadata_for_unknown_item_returns_empty_not_none(isolated_state):
    assert fabric_catalog.get_metadata("does-not-exist") == {"description": "", "relationships": []}


def test_set_metadata_rejects_an_unknown_relationship_type(isolated_state):
    with pytest.raises(ValueError, match="relación"):
        fabric_catalog.set_metadata("nb-1", description="", relationships=[{"type": "deletes", "target_item_id": "x"}])


def test_set_metadata_rejects_a_relationship_missing_a_target(isolated_state):
    with pytest.raises(ValueError):
        fabric_catalog.set_metadata("nb-1", description="", relationships=[{"type": "reads_from", "target_item_id": ""}])


def test_set_metadata_rejects_self_referencing_relationship(isolated_state):
    with pytest.raises(ValueError, match="sí mismo|consigo"):
        fabric_catalog.set_metadata("nb-1", description="", relationships=[{"type": "writes_to", "target_item_id": "nb-1"}])


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
