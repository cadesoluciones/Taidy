# -*- coding: utf-8 -*-
"""
src/bc_client/config.py:_read_tables/_parse_table_entry -- BC tables are
identical between environments except for the `{ENVIRONMENT}` path segment
in each table's `url`, which is substituted with the resolved
BC_ENVIRONMENT value (see src/config_loader.py:resolve_environment) when
`tables.yaml` is loaded. There is a single `tables.yaml`, never one file
per environment.
"""

from __future__ import annotations

import sys
from pathlib import Path

from src.bc_client.config import _read_tables

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def test_read_tables_substitutes_the_environment_placeholder(tmp_path: Path):
    (tmp_path / "tables.yaml").write_text(
        "tables:\n"
        "  - name: t1\n"
        "    url: https://example/{ENVIRONMENT}/odata/T1\n",
        encoding="utf-8",
    )

    prod_tables = _read_tables(tmp_path, {"BC_ENVIRONMENT": "PRODUCTION"})
    assert [t.url for t in prod_tables] == ["https://example/PRODUCTION/odata/T1"]

    sandbox_tables = _read_tables(tmp_path, {"BC_ENVIRONMENT": "SANDBOX"})
    assert [t.url for t in sandbox_tables] == ["https://example/SANDBOX/odata/T1"]


def test_read_tables_leaves_urls_without_a_placeholder_unchanged(tmp_path: Path):
    (tmp_path / "tables.yaml").write_text(
        "tables:\n"
        "  - name: t1\n"
        "    url: https://example/odata/T1\n",
        encoding="utf-8",
    )

    tables = _read_tables(tmp_path, {"BC_ENVIRONMENT": "SANDBOX"})
    assert [t.url for t in tables] == ["https://example/odata/T1"]


def test_read_tables_defaults_to_sandbox_cade_when_bc_environment_unset(tmp_path: Path):
    (tmp_path / "tables.yaml").write_text(
        "tables:\n"
        "  - name: t1\n"
        "    url: https://example/{ENVIRONMENT}/odata/T1\n",
        encoding="utf-8",
    )

    tables = _read_tables(tmp_path, {})
    assert [t.url for t in tables] == ["https://example/SANDBOX_CADE/odata/T1"]


def test_read_tables_raises_clear_error_when_tables_file_missing(tmp_path: Path):
    import pytest

    with pytest.raises(ValueError, match="tables.yaml"):
        _read_tables(tmp_path, {"BC_ENVIRONMENT": "SANDBOX"})
