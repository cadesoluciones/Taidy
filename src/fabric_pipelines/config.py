# -*- coding: utf-8 -*-
"""
Configuration for triggering Microsoft Fabric Data Factory pipelines on demand.

Credentials (tenant_id, client_id, client_secret) are intentionally reused
from the existing `business_central_upload` config section — the same
service principal already used to write into OneLake, provided it also has
at least Contributor access on the workspace so it's allowed to run
pipeline jobs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from src.config_loader import load_config_data

REQUIRED_SECRET_KEYS = ["FABRIC_CLIENT_SECRET"]


@dataclass
class PipelineConfig:
    name: str
    item_id: str


@dataclass
class Settings:
    tenant_id: str
    client_id: str
    client_secret: str
    workspace_id: str
    pipelines: List[PipelineConfig]

    def get_pipeline(self, name: str) -> PipelineConfig:
        for p in self.pipelines:
            if p.name == name:
                return p
        available = ", ".join(p.name for p in self.pipelines) or "(ninguno configurado)"
        raise ValueError(f"Pipeline desconocido: '{name}'. Configurados: {available}")


def _workspace_id(section: dict) -> Optional[str]:
    """Soft lookup of section['workspace_id'] -- this section's own value is
    optional (it can fall back to business_central_upload's), so a missing
    value here just means "nothing to fall back to", not an error."""
    value = section.get("workspace_id")
    return str(value).strip() if value else None


def load_settings(
    env: Optional[Iterable[tuple[str, str]]] = None,
    *,
    config_data: dict | None = None,
    config_file: Path | str | None = None,
    config_dir: Optional[Path] = None,
) -> Settings:
    raw_env = dict(env or os.environ.items())
    missing = [k for k in REQUIRED_SECRET_KEYS if not raw_env.get(k)]
    if missing:
        raise ValueError(f"Missing required configuration: {', '.join(missing)}")

    if config_data is not None:
        data = config_data
    else:
        data, _root = load_config_data(config_file)

    bc_upload = data.get("business_central_upload")
    if not isinstance(bc_upload, dict):
        raise ValueError(
            "Configuration file missing 'business_central_upload' section (its credentials are reused here)"
        )

    section = data.get("fabric_pipelines")
    if not isinstance(section, dict):
        raise ValueError("Configuration file missing 'fabric_pipelines' section")

    workspace_id = _workspace_id(section) or _workspace_id(bc_upload)
    if not workspace_id:
        raise ValueError("No 'workspace_id' configured in 'fabric_pipelines' or 'business_central_upload'")

    raw_pipelines = section.get("pipelines") or []
    if not isinstance(raw_pipelines, list):
        raise ValueError("'fabric_pipelines.pipelines' must be a list of {'name', 'item_id'} entries")

    pipelines: List[PipelineConfig] = []
    for entry in raw_pipelines:
        if not isinstance(entry, dict) or not entry.get("name") or not entry.get("item_id"):
            raise ValueError(f"Invalid pipeline entry {entry!r}: needs non-empty 'name' and 'item_id'")
        pipelines.append(PipelineConfig(name=str(entry["name"]), item_id=str(entry["item_id"])))

    return Settings(
        tenant_id=bc_upload["tenant_id"].strip(),
        client_id=bc_upload["client_id"].strip(),
        client_secret=raw_env["FABRIC_CLIENT_SECRET"].strip(),
        workspace_id=str(workspace_id).strip(),
        pipelines=pipelines,
    )
