"""Configuration helpers for Fabric OneLake uploads."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from src.config_loader import load_config_data


@dataclass
class FabricUploadSettings:
    """Validated configuration needed to push CSV files to Fabric OneLake."""

    tenant_id: str
    client_id: str
    client_secret: str
    workspace_name: str
    lakehouse_name: str
    workspace_id: Optional[str]
    lakehouse_id: Optional[str]
    path_prefix: str
    source_name: str
    checkpoint_path: str
    overwrite: bool
    max_retries: int
    local_export_root: Path


REQUIRED_SECRET_KEYS = ["FABRIC_CLIENT_SECRET"]


def load_fabric_settings(
    output_dir: Path,
    env: Optional[Iterable[tuple[str, str]]] = None,
    *,
    force_enable: bool = False,
    config_data: dict | None = None,
    config_file: Path | str | None = None,
    config_dir: Optional[Path] = None,
    checkpoint_path_override: Optional[str] = None,
) -> Optional[FabricUploadSettings]:
    """Load Fabric upload settings from configuration + secrets."""

    env_data = dict(env or os.environ.items())
    _require_keys(env_data, REQUIRED_SECRET_KEYS)

    config_section, _ = _resolve_fabric_config(config_data, config_file, config_dir)
    enabled_flag = config_section.get("enabled", True)
    enabled = (
        force_enable
        or _is_true(env_data.get("FABRIC_UPLOAD_ENABLED"))
        or bool(enabled_flag)
    )
    if not enabled:
        return None

    path_prefix = _normalize_prefix(config_section.get("path_prefix", "raw"))
    source_name = _sanitize_segment(
        config_section.get("source_name", "business_central")
    )
    checkpoint_source = checkpoint_path_override or config_section.get(
        "checkpoint_path", "raw/checkpoints/business_central"
    )
    checkpoint_path = _normalize_prefix(checkpoint_source)
    overwrite = bool(config_section.get("overwrite", True))
    max_retries = _parse_retries(str(config_section.get("max_retries", 3)))

    return FabricUploadSettings(
        tenant_id=config_section["tenant_id"].strip(),
        client_id=config_section["client_id"].strip(),
        client_secret=env_data["FABRIC_CLIENT_SECRET"].strip(),
        workspace_name=config_section["workspace_name"].strip(),
        lakehouse_name=config_section["lakehouse_name"].strip(),
        workspace_id=(config_section.get("workspace_id") or "").strip() or None,
        lakehouse_id=(config_section.get("lakehouse_id") or "").strip() or None,
        path_prefix=path_prefix,
        source_name=source_name,
        checkpoint_path=checkpoint_path,
        overwrite=overwrite,
        max_retries=max_retries,
        local_export_root=output_dir.expanduser().resolve(),
    )


def _resolve_fabric_config(
    config_data: dict | None,
    config_file: Path | str | None,
    config_dir: Optional[Path],
) -> tuple[dict[str, Any], Path]:
    if config_data is not None:
        section = config_data.get("fabric_upload")
        if not isinstance(section, dict):
            raise ValueError("Configuration file missing 'fabric_upload' section")
        return section, config_dir or Path.cwd()

    data, root = load_config_data(config_file)
    section = data.get("fabric_upload")
    if not isinstance(section, dict):
        raise ValueError("Configuration file missing 'fabric_upload' section")
    return section, root


def _require_keys(env: Dict[str, str], keys: Iterable[str]) -> None:
    missing = [key for key in keys if not env.get(key)]
    if missing:
        raise ValueError(
            "Missing required Fabric upload configuration: "
            + ", ".join(sorted(missing))
        )


def _is_true(value: Optional[str]) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _normalize_prefix(value: str) -> str:
    cleaned = value.strip().strip("/")
    if not cleaned:
        raise ValueError("FABRIC_PATH_PREFIX must be a non-empty path")
    return cleaned


def _sanitize_segment(raw: str) -> str:
    cleaned = raw.strip().lower().replace(" ", "_")
    cleaned = "".join(ch for ch in cleaned if ch.isalnum() or ch in {"-", "_"})
    cleaned = cleaned.strip("_-")
    if not cleaned:
        raise ValueError("FABRIC_SOURCE_NAME must contain alphanumeric characters")
    return cleaned


def _parse_retries(raw: str) -> int:
    try:
        retries = int(raw)
    except ValueError as exc:  # pragma: no cover - defensive
        raise ValueError("FABRIC_MAX_RETRIES must be a positive integer") from exc
    if retries <= 0:
        raise ValueError("FABRIC_MAX_RETRIES must be greater than zero")
    return retries
