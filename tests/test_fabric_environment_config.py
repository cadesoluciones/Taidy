# -*- coding: utf-8 -*-
"""
Workspace/lakehouse resolution for src/fabric_upload/config.py and
src/fabric_pipelines/config.py -- flat workspace_name/workspace_id keys on
the section itself, no per-environment nesting (Fabric has no concept of
environment, unlike Business Central's BC_ENVIRONMENT). The config.json
section is named `business_central_upload` (source-named, like
factorial_upload/hubspot_upload), not `fabric_upload` -- the destination
(Fabric) is the same for all three, so naming by destination was redundant.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.fabric_pipelines.config import load_settings as load_pipelines_settings  # noqa: E402
from src.fabric_upload.config import load_fabric_settings  # noqa: E402


def test_load_fabric_settings_reads_the_flat_workspace_block(tmp_path):
    config = {
        "business_central_upload": {
            "tenant_id": "t",
            "client_id": "c",
            "path_prefix": "raw",
            "source_name": "business_central",
            "workspace_name": "prod-ws",
            "lakehouse_name": "prod-lh",
        }
    }

    settings = load_fabric_settings(tmp_path, env=[("FABRIC_CLIENT_SECRET", "s")], config_data=config)
    assert settings.workspace_name == "prod-ws"
    assert settings.lakehouse_name == "prod-lh"


def test_load_fabric_settings_raises_clear_error_when_workspace_name_missing(tmp_path):
    config = {
        "business_central_upload": {
            "tenant_id": "t",
            "client_id": "c",
            "path_prefix": "raw",
            "source_name": "business_central",
            "lakehouse_name": "prod-lh",
        }
    }

    with pytest.raises(KeyError):
        load_fabric_settings(tmp_path, env=[("FABRIC_CLIENT_SECRET", "s")], config_data=config)


def test_fabric_pipelines_falls_back_to_business_central_upload_workspace_id():
    config = {
        "business_central_upload": {
            "tenant_id": "t",
            "client_id": "c",
            "workspace_id": "from-bc-upload",
        },
        "fabric_pipelines": {"pipelines": []},
    }

    settings = load_pipelines_settings(env=[("FABRIC_CLIENT_SECRET", "s")], config_data=config)
    assert settings.workspace_id == "from-bc-upload"


def test_fabric_pipelines_own_workspace_id_wins_over_fallback():
    config = {
        "business_central_upload": {
            "tenant_id": "t",
            "client_id": "c",
            "workspace_id": "from-bc-upload",
        },
        "fabric_pipelines": {
            "workspace_id": "own-workspace",
            "pipelines": [],
        },
    }

    settings = load_pipelines_settings(env=[("FABRIC_CLIENT_SECRET", "s")], config_data=config)
    assert settings.workspace_id == "own-workspace"


def test_fabric_pipelines_raises_when_no_workspace_id_anywhere():
    config = {
        "business_central_upload": {"tenant_id": "t", "client_id": "c"},
        "fabric_pipelines": {"pipelines": []},
    }

    with pytest.raises(ValueError, match="workspace_id"):
        load_pipelines_settings(env=[("FABRIC_CLIENT_SECRET", "s")], config_data=config)
