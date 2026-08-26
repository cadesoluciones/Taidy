# -*- coding: utf-8 -*-
"""
NEW-02: adding new Business Central / Factorial tables from the web UI
instead of hand-editing tables.yaml / factorial_tables.yaml on the server.

Every test points table_configs at throwaway files under tmp_path -- never
the real tables.yaml / factorial_tables.yaml at the project root.
"""

from __future__ import annotations

import pytest

from webapp import table_configs


@pytest.fixture(autouse=True)
def isolated_table_files(tmp_path, monkeypatch):
    monkeypatch.setattr(table_configs, "_BC_TABLES_PATH", tmp_path / "tables.yaml")
    monkeypatch.setattr(table_configs, "_FACTORIAL_TABLES_PATH", tmp_path / "factorial_tables.yaml")


# --------------------------------------------------------------------------------------
# Business Central
# --------------------------------------------------------------------------------------


def test_list_bc_tables_full_is_empty_when_file_missing():
    assert table_configs.list_bc_tables_full() == []


def test_add_bc_table_then_list_round_trips():
    table_configs.add_bc_table("bc_new_table", "https://example/odata/NewTable", description="desc", incremental=True)
    tables = table_configs.list_bc_tables_full()
    assert tables == [
        {"name": "bc_new_table", "description": "desc", "url": "https://example/odata/NewTable", "incremental": True}
    ]


def test_write_never_creates_a_sibling_tmp_file(tmp_path):
    """Regression guard: tables.yaml/hubspot_tables.yaml/factorial_tables.yaml
    are each individually bind-mounted single files in production (see
    docker-compose.yml) -- writing to a sibling .tmp file and renaming it
    over the real target fails there with "OSError: [Errno 16] Device or
    resource busy" (confirmed live). _write() must write straight into the
    target path instead, never via a .tmp + rename dance."""
    table_configs.add_bc_table("bc_new_table", "https://example/odata/NewTable")
    assert not (tmp_path / "tables.tmp").exists()
    assert (tmp_path / "tables.yaml").is_file()


def test_add_bc_table_rejects_duplicate_name():
    table_configs.add_bc_table("bc_dup", "https://example/odata/A")
    with pytest.raises(ValueError, match="Ya existe"):
        table_configs.add_bc_table("bc_dup", "https://example/odata/B")


def test_add_bc_table_requires_name_and_url():
    with pytest.raises(ValueError, match="nombre"):
        table_configs.add_bc_table("", "https://example/odata/A")
    with pytest.raises(ValueError, match="URL"):
        table_configs.add_bc_table("bc_x", "")


def test_update_bc_table_changes_url_description_and_incremental():
    table_configs.add_bc_table("bc_edit", "https://example/odata/Old", description="old desc")
    entry = table_configs.update_bc_table(
        "bc_edit", "https://example/odata/New", description="new desc", incremental=True
    )
    assert entry == {
        "name": "bc_edit",
        "description": "new desc",
        "url": "https://example/odata/New",
        "incremental": True,
    }
    assert table_configs.list_bc_tables_full() == [entry]


def test_update_bc_table_requires_url():
    table_configs.add_bc_table("bc_edit", "https://example/odata/Old")
    with pytest.raises(ValueError, match="URL"):
        table_configs.update_bc_table("bc_edit", "")


def test_update_bc_table_rejects_unknown_name():
    with pytest.raises(ValueError, match="No existe"):
        table_configs.update_bc_table("does-not-exist", "https://example/odata/X")


def test_delete_bc_table_removes_only_the_matching_entry():
    table_configs.add_bc_table("bc_keep", "https://example/odata/Keep")
    table_configs.add_bc_table("bc_remove", "https://example/odata/Remove")
    table_configs.delete_bc_table("bc_remove")
    names = [t["name"] for t in table_configs.list_bc_tables_full()]
    assert names == ["bc_keep"]


def test_delete_bc_table_is_a_no_op_for_unknown_name():
    table_configs.add_bc_table("bc_keep", "https://example/odata/Keep")
    table_configs.delete_bc_table("does-not-exist")
    assert len(table_configs.list_bc_tables_full()) == 1


# --------------------------------------------------------------------------------------
# Factorial HR
# --------------------------------------------------------------------------------------


def test_list_factorial_tables_full_is_empty_when_file_missing():
    assert table_configs.list_factorial_tables_full() == []


def test_add_factorial_table_then_list_round_trips():
    entry = table_configs.add_factorial_table(
        "factorial_new",
        "resources/new/endpoint",
        ["id", "name"],
        description="desc",
        date_range=False,
        employee_filter=False,
        incremental=True,
        overlap_days=3,
        chunk_days=30,
    )
    assert entry == {
        "name": "factorial_new",
        "description": "desc",
        "path": "resources/new/endpoint",
        "date_range": False,
        "employee_filter": False,
        "incremental": True,
        "fields": ["id", "name"],
        "overlap_days": 3,
        "chunk_days": 30,
    }
    assert table_configs.list_factorial_tables_full() == [entry]


def test_add_factorial_table_omits_optional_ints_when_not_given():
    entry = table_configs.add_factorial_table("factorial_min", "resources/x", ["id"])
    assert "overlap_days" not in entry
    assert "chunk_days" not in entry
    assert entry["date_range"] is True
    assert entry["employee_filter"] is True
    assert entry["incremental"] is False


def test_add_factorial_table_requires_name_path_and_fields():
    with pytest.raises(ValueError, match="nombre"):
        table_configs.add_factorial_table("", "resources/x", ["id"])
    with pytest.raises(ValueError, match="ruta"):
        table_configs.add_factorial_table("factorial_x", "", ["id"])
    with pytest.raises(ValueError, match="campo"):
        table_configs.add_factorial_table("factorial_x", "resources/x", [])
    with pytest.raises(ValueError, match="campo"):
        table_configs.add_factorial_table("factorial_x", "resources/x", ["  ", ""])


def test_add_factorial_table_rejects_duplicate_name():
    table_configs.add_factorial_table("factorial_dup", "resources/a", ["id"])
    with pytest.raises(ValueError, match="Ya existe"):
        table_configs.add_factorial_table("factorial_dup", "resources/b", ["id"])


def test_update_factorial_table_changes_fields_and_clears_stale_optional_ints():
    table_configs.add_factorial_table(
        "factorial_edit", "resources/old", ["id"], description="old", overlap_days=5, chunk_days=10
    )
    entry = table_configs.update_factorial_table(
        "factorial_edit",
        "resources/new",
        ["id", "name"],
        description="new",
        date_range=False,
        employee_filter=False,
        incremental=True,
        overlap_days=None,
        chunk_days=None,
    )
    assert entry == {
        "name": "factorial_edit",
        "description": "new",
        "path": "resources/new",
        "date_range": False,
        "employee_filter": False,
        "incremental": True,
        "fields": ["id", "name"],
    }
    assert table_configs.list_factorial_tables_full() == [entry]


def test_update_factorial_table_requires_path_and_fields():
    table_configs.add_factorial_table("factorial_edit", "resources/old", ["id"])
    with pytest.raises(ValueError, match="ruta"):
        table_configs.update_factorial_table("factorial_edit", "", ["id"])
    with pytest.raises(ValueError, match="campo"):
        table_configs.update_factorial_table("factorial_edit", "resources/x", [])


def test_update_factorial_table_rejects_unknown_name():
    with pytest.raises(ValueError, match="No existe"):
        table_configs.update_factorial_table("does-not-exist", "resources/x", ["id"])


def test_delete_factorial_table_removes_only_the_matching_entry():
    table_configs.add_factorial_table("factorial_keep", "resources/keep", ["id"])
    table_configs.add_factorial_table("factorial_remove", "resources/remove", ["id"])
    table_configs.delete_factorial_table("factorial_remove")
    names = [t["name"] for t in table_configs.list_factorial_tables_full()]
    assert names == ["factorial_keep"]
