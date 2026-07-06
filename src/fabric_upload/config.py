# -*- coding: utf-8 -*-
"""
Configuration loading, validation, and data models for Fabric OneLake uploads.

This module is responsible for consolidating settings from the `fabric_upload`
section of the main JSON config file and relevant environment variables into a
single, type-safe `FabricUploadSettings` object. It handles validation, default
values, and normalization for all upload-related configuration.
"""

# --------------------------------------------------------------------------------------
# Imports
# --------------------------------------------------------------------------------------

import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, Optional

from src.config_loader import load_config_data
from src.utils import sanitize_segment

# --------------------------------------------------------------------------------------
# Data Models
# --------------------------------------------------------------------------------------


@dataclass
class FabricUploadSettings:
    """
    A container for all validated configuration needed to push CSV files to Fabric OneLake.
    """

    # --- Authentication and Endpoint Details ---
    tenant_id: str
    client_id: str
    client_secret: str
    workspace_name: str
    lakehouse_name: str
    workspace_id: Optional[str]
    lakehouse_id: Optional[str]

    # --- Path and Naming Configuration ---
    remote_base: PurePosixPath
    checkpoint_root: PurePosixPath
    local_export_root: Path

    # --- Behavior Configuration ---
    overwrite: bool
    max_retries: int


# --------------------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------------------

# REQUIRED_SECRET_KEYS lists environment variables that must be set for Fabric uploads.
REQUIRED_SECRET_KEYS = ["FABRIC_CLIENT_SECRET"]


# --------------------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------------------


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
    """
    Loads and validates all Fabric upload settings from various sources.

    If uploads are disabled (via config or environment variable) and not
    `force_enable`'d, this function returns `None`.

    Args:
        output_dir: The local directory containing the files to be uploaded. This
                    becomes the `local_export_root`.
        env: Optional environment variables for testing.
        force_enable: If True, bypasses the 'enabled' flag and always returns settings.
        config_data: Optional pre-loaded config data for testing.
        config_file: Optional path to the main JSON config file.
        config_dir: Optional path to the directory of the config file.
        checkpoint_path_override: Optional override for the checkpoint path.

    Returns:
        A fully validated `FabricUploadSettings` object, or `None` if uploads
        are disabled.
    """
    env_data = dict(env or os.environ.items())
    _require_keys(env_data, REQUIRED_SECRET_KEYS)

    config_section, _ = _resolve_fabric_config(config_data, config_file, config_dir)

    # Determine if uploads are enabled. `force_enable` takes highest precedence.
    enabled_flag = config_section.get("enabled", True)
    enabled = (
        force_enable
        or _is_true(env_data.get("FABRIC_UPLOAD_ENABLED"))
        or bool(enabled_flag)
    )
    if not enabled:
        return None

    # Normalize and sanitize path components to ensure they are safe for URLs.
    path_prefix = _normalize_prefix(config_section.get("path_prefix", "raw"))
    checkpoint_source = checkpoint_path_override or config_section.get(
        "checkpoint_path", "raw/checkpoints/business_central"
    )
    checkpoint_path = _normalize_prefix(checkpoint_source)
    remote_base = PurePosixPath(path_prefix) / sanitize_segment(
        config_section.get("source_name", "business_central")
    )
    checkpoint_root = PurePosixPath(checkpoint_path)

    # Parse behavioral flags.
    overwrite = bool(config_section.get("overwrite", True))
    max_retries = _parse_retries(str(config_section.get("max_retries", 3)))

    # Construct the final settings object, stripping whitespace from all string inputs.
    return FabricUploadSettings(
        tenant_id=config_section["tenant_id"].strip(),
        client_id=config_section["client_id"].strip(),
        client_secret=env_data["FABRIC_CLIENT_SECRET"].strip(),
        workspace_name=config_section["workspace_name"].strip(),
        lakehouse_name=config_section["lakehouse_name"].strip(),
        workspace_id=(config_section.get("workspace_id") or "").strip() or None,
        lakehouse_id=(config_section.get("lakehouse_id") or "").strip() or None,
        remote_base=remote_base,
        checkpoint_root=checkpoint_root,
        overwrite=overwrite,
        max_retries=max_retries,
        local_export_root=Path(output_dir).expanduser().resolve(),
    )


# --------------------------------------------------------------------------------------
# Internal Helper Functions
# --------------------------------------------------------------------------------------


def _resolve_fabric_config(
    config_data: dict | None,
    config_file: Path | str | None,
    config_dir: Optional[Path],
) -> tuple[dict[str, Any], Path]:
    """
    Loads the main JSON config and extracts the 'fabric_upload' section.
    """
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
    """
    Ensures that required secret keys are present in the environment.
    """
    missing = [key for key in keys if not env.get(key)]
    if missing:
        raise ValueError(
            "Missing required Fabric upload configuration: "
            + ", ".join(sorted(missing))
        )


def _is_true(value: Optional[str]) -> bool:
    """
    Checks if a string value represents 'true'. Case-insensitive.
    """
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _normalize_prefix(value: str) -> str:
    """
    Normalizes a path prefix by removing leading/trailing slashes.
    """
    cleaned = value.strip().strip("/")
    if not cleaned:
        raise ValueError("Path prefix values must not be empty.")
    return cleaned


def _parse_retries(raw: str) -> int:
    """
    Parses the number of retries, ensuring it is a positive integer.
    """
    try:
        retries = int(raw)
    except (ValueError, TypeError) as exc:  # pragma: no cover
        raise ValueError("Max retries must be a positive integer.") from exc
    if retries <= 0:
        raise ValueError("Max retries must be greater than zero.")
    return retries
