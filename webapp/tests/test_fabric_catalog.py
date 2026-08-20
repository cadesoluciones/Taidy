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
    assert pipeline["color"] == ""
    assert pipeline["icon"] == ""
    assert pipeline["canvas_positions"] == {}


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
        "color": "",
        "icon": "",
        "canvas_positions": {},
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
    positions -- api/routers/fabric_catalog.py must read the existing ones
    and pass them straight through, not silently clear the canvas."""
    fabric_catalog.set_canvas_positions("nb-1", {"pl-1": {"x": 5, "y": 6}})
    _set("nb-1", short_description="Facturas")
    assert fabric_catalog.get_metadata("nb-1")["canvas_positions"] == {"pl-1": {"x": 5, "y": 6}}


def test_add_relationship_appends_without_touching_other_fields(isolated_state):
    _set("nb-1", short_description="Facturas", owners=["jose"])
    entry = fabric_catalog.add_relationship("nb-1", "reads_from", "lh-bronze", reviewed_by="admin1")
    assert entry["relationships"] == [{"type": "reads_from", "target_item_id": "lh-bronze"}]
    assert entry["short_description"] == "Facturas"
    assert entry["owners"] == ["jose"]
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
    entirely (it's neither a live Fabric item nor recognized as custom)."""
    created = fabric_catalog.create_custom_item("Excel de ventas", "Fuente externa", created_by="admin1")
    item_id = created["item_id"]
    fabric_catalog.set_metadata(
        item_id,
        short_description="Datos de ventas mensuales",
        long_description_markdown="",
        owners=[],
        criticality="",
        status="",
        tags=[],
        relationships=[],
        reviewed_by="admin2",
    )
    stored = fabric_catalog.get_metadata(item_id)
    assert stored["is_custom"] is True
    assert stored["name"] == "Excel de ventas"
    assert stored["type"] == "Fuente externa"
    assert stored["short_description"] == "Datos de ventas mensuales"


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
