# -*- coding: utf-8 -*-
"""
webapp/config_settings.py -- the admin-editable view over config.json's
non-secret connection parameters (tenant/client/workspace/lakehouse ids,
retry/paging tuning, notifications, Fabric pipeline mappings).
"""

from __future__ import annotations

import json
import os

import pytest

from webapp import config_settings

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
        "path_prefix": "raw",
        "source_name": "business_central",
    },
    "factorial_upload": {
        "tenant_id": "old-tenant",
        "client_id": "old-upload-client",
        "workspace_id": "ws-1",
        "workspace_name": "Sandbox",
        "lakehouse_id": "lh-1",
        "lakehouse_name": "Lakehouse",
        "max_retries": 3,
        "path_prefix": "raw",
        "source_name": "factorial",
    },
    "hubspot_upload": {
        "tenant_id": "old-tenant",
        "client_id": "old-upload-client",
        "workspace_id": "ws-1",
        "workspace_name": "Sandbox",
        "lakehouse_id": "lh-1",
        "lakehouse_name": "Lakehouse",
        "max_retries": 3,
        "path_prefix": "raw",
        "source_name": "hubspot",
    },
    "fabric_pipelines": {
        "pipelines": [
            {"name": "Pipeline_CADE", "item_id": "pl-1"},
            {"name": "Pipeline_CADE_Bronce", "item_id": "pl-2"},
        ]
    },
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
def _isolated_config_path(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(_BASE_CONFIG, indent=2), encoding="utf-8")
    monkeypatch.setenv("CONFIG_FILE", str(config_path))
    yield config_path


def _read_raw(config_path):
    return json.loads(config_path.read_text(encoding="utf-8"))


def test_list_fields_reads_current_values(_isolated_config_path):
    fields = {f["key"]: f for f in config_settings.list_fields()}
    assert fields["bc_tenant_id"]["value"] == "old-tenant"
    assert fields["bc_page_size"]["value"] == 1000
    assert fields["fabric_upload_enabled"]["value"] is True
    assert fields["notifications_admin_recipients"]["value"] == []


def test_set_field_writes_a_single_section_field(_isolated_config_path):
    result = config_settings.set_field("bc_company_name", "Nueva Empresa SL")
    assert result["value"] == "Nueva Empresa SL"
    raw = _read_raw(_isolated_config_path)
    assert raw["business_central"]["company_name"] == "Nueva Empresa SL"


def test_set_field_recomputes_bc_token_url_from_tenant_id(_isolated_config_path):
    config_settings.set_field("bc_tenant_id", "new-tenant-guid")
    raw = _read_raw(_isolated_config_path)
    assert raw["business_central"]["tenant_id"] == "new-tenant-guid"
    assert raw["business_central"]["token_url"] == (
        "https://login.microsoftonline.com/new-tenant-guid/oauth2/v2.0/token"
    )


def test_set_field_writes_a_shared_value_to_every_upload_section_at_once(_isolated_config_path):
    """fabric_upload_* fields are one logical value duplicated across
    business_central_upload/factorial_upload/hubspot_upload -- saving one
    must update all three, or the three uploaders would silently start
    pointing at different workspaces."""
    config_settings.set_field("fabric_upload_workspace_id", "ws-new")
    raw = _read_raw(_isolated_config_path)
    assert raw["business_central_upload"]["workspace_id"] == "ws-new"
    assert raw["factorial_upload"]["workspace_id"] == "ws-new"
    assert raw["hubspot_upload"]["workspace_id"] == "ws-new"
    # Untouched sibling fields in those same sections must survive.
    assert raw["factorial_upload"]["lakehouse_id"] == "lh-1"


def test_set_field_boolean(_isolated_config_path):
    result = config_settings.set_field("fabric_upload_enabled", False)
    assert result["value"] is False
    raw = _read_raw(_isolated_config_path)
    assert raw["business_central_upload"]["enabled"] is False


def test_set_field_number_rejects_a_non_integer(_isolated_config_path):
    with pytest.raises(ValueError, match="número entero"):
        config_settings.set_field("bc_page_size", "not-a-number")


def test_set_field_list_cleans_and_dedupes(_isolated_config_path):
    result = config_settings.set_field(
        "notifications_admin_recipients", ["  a@x.com ", "b@x.com", "a@x.com", "  "]
    )
    assert result["value"] == ["a@x.com", "b@x.com"]


def test_set_field_rejects_an_unknown_key(_isolated_config_path):
    with pytest.raises(ValueError, match="no es una clave reconocida"):
        config_settings.set_field("not_a_real_field", "x")


def test_set_field_never_renames_onto_the_real_config_path(_isolated_config_path, monkeypatch):
    """Same production risk as webapp/tests/test_env_secrets.py's
    equivalent regression test: config.json is a Docker single-file bind
    mount, so a rename onto it must never be attempted."""
    real_replace = os.replace

    def _guarded_replace(src, dst):
        if os.fspath(dst) == os.fspath(_isolated_config_path):
            raise OSError(16, "Device or resource busy")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", _guarded_replace)

    result = config_settings.set_field("bc_company_name", "Nueva Empresa SL")

    assert result["value"] == "Nueva Empresa SL"
    assert _read_raw(_isolated_config_path)["business_central"]["company_name"] == "Nueva Empresa SL"


def test_list_pipelines(_isolated_config_path):
    assert config_settings.list_pipelines() == [
        {"name": "Pipeline_CADE", "item_id": "pl-1"},
        {"name": "Pipeline_CADE_Bronce", "item_id": "pl-2"},
    ]


def test_set_pipelines_replaces_the_whole_list(_isolated_config_path):
    new_list = [{"name": "Pipeline_CADE_Gold", "item_id": "pl-9"}]
    result = config_settings.set_pipelines(new_list)
    assert result == new_list
    assert config_settings.list_pipelines() == new_list


def test_set_pipelines_rejects_a_blank_name_or_item_id(_isolated_config_path):
    with pytest.raises(ValueError, match="nombre y un item_id"):
        config_settings.set_pipelines([{"name": "", "item_id": "pl-1"}])
    with pytest.raises(ValueError, match="nombre y un item_id"):
        config_settings.set_pipelines([{"name": "Foo", "item_id": ""}])


def test_set_pipelines_rejects_duplicate_names(_isolated_config_path):
    with pytest.raises(ValueError, match="repetido"):
        config_settings.set_pipelines(
            [{"name": "Foo", "item_id": "pl-1"}, {"name": "Foo", "item_id": "pl-2"}]
        )
