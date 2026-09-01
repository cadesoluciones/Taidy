# -*- coding: utf-8 -*-
from __future__ import annotations

from webapp import fabric_catalog_cache


def test_merge_and_get_upserts_live_facts_and_stamps_last_synced_at(isolated_state):
    cache = fabric_catalog_cache.merge_and_get({"nb-1": {"name": "silver_facturas", "type": "Notebook", "folder_path": ["Fabric"]}})
    assert cache["nb-1"]["name"] == "silver_facturas"
    assert cache["nb-1"]["last_synced_at"] != ""


def test_merge_and_get_keeps_earlier_entries_not_seen_this_time(isolated_state):
    fabric_catalog_cache.merge_and_get({"nb-1": {"name": "silver_facturas", "type": "Notebook", "folder_path": ["Fabric"]}})
    cache = fabric_catalog_cache.merge_and_get({})  # this round saw nothing live
    assert "nb-1" in cache


def test_merge_and_get_refreshes_last_synced_at_on_every_live_sighting(isolated_state):
    first = fabric_catalog_cache.merge_and_get({"nb-1": {"name": "a", "type": "Notebook", "folder_path": []}})
    first_stamp = first["nb-1"]["last_synced_at"]
    second = fabric_catalog_cache.merge_and_get({"nb-1": {"name": "a", "type": "Notebook", "folder_path": []}})
    assert second["nb-1"]["last_synced_at"] >= first_stamp


def test_delete_entry_removes_a_cached_item(isolated_state):
    fabric_catalog_cache.merge_and_get({"nb-1": {"name": "a", "type": "Notebook", "folder_path": []}})
    fabric_catalog_cache.delete_entry("nb-1")
    assert "nb-1" not in fabric_catalog_cache.list_cached_ids()


def test_delete_entry_on_an_unknown_id_is_a_no_op(isolated_state):
    fabric_catalog_cache.delete_entry("does-not-exist")  # must not raise
    assert fabric_catalog_cache.list_cached_ids() == []


def test_list_cached_ids_empty_when_nothing_ever_synced(isolated_state):
    assert fabric_catalog_cache.list_cached_ids() == []
