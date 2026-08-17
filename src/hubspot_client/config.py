# -*- coding: utf-8 -*-
"""
Configuration loading for the HubSpot CRM client.

Reads HUBSPOT_API_KEY (a Private App access token) from the environment.
Table definitions -- which CRM object type to extract and which properties
to keep -- are loaded from the YAML file referenced in config.json.

Extraction is full-only for now: unlike Factorial, there is no date range,
employee filter, or checkpoint-based incremental mode.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml

from src.config_loader import load_config_data

# --------------------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------------------

HUBSPOT_BASE_URL = "https://api.hubapi.com"

REQUIRED_ENV_KEYS = ["HUBSPOT_API_KEY"]

DEFAULT_OUTPUT_DIR = "./exports_hubspot"


# --------------------------------------------------------------------------------------
# Data Models
# --------------------------------------------------------------------------------------


@dataclass
class TableConfig:
    """Represents a single HubSpot CRM object type to fetch (contacts, companies, deals...)."""

    name: str
    object_type: str
    fields: List[str]
    description: str = ""


@dataclass
class Settings:
    """All settings required to call the HubSpot CRM API."""

    api_key: str
    tables: List[TableConfig]
    base_url: str = HUBSPOT_BASE_URL
    output_dir: Path = None  # resolved in load_settings


# --------------------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------------------


def load_settings(
    env: Optional[Iterable[tuple[str, str]]] = None,
    *,
    config_data: dict | None = None,
    config_file: Path | str | None = None,
    config_dir: Optional[Path] = None,
) -> Settings:
    """
    Loads HubSpot settings from environment variables and config files.

    Args:
        env: Optional iterable of (key, value) pairs, primarily for testing.
        config_data: Optional pre-loaded config dict, for testing.
        config_file: Optional path to the main JSON config file.
        config_dir: Optional directory of the config file.

    Raises:
        ValueError: If required env vars or config sections are missing.

    Returns:
        A populated Settings object.
    """
    raw_env = dict(env or os.environ.items())

    missing = [k for k in REQUIRED_ENV_KEYS if not raw_env.get(k)]
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

    config_section, config_root = _resolve_hubspot_config(config_data, config_file, config_dir)

    tables = _load_tables(config_section, config_root)
    output_dir = _read_output_dir(config_section, config_root)

    return Settings(
        api_key=raw_env["HUBSPOT_API_KEY"],
        base_url=config_section.get("base_url", HUBSPOT_BASE_URL),
        tables=tables,
        output_dir=output_dir,
    )


# --------------------------------------------------------------------------------------
# Internal helpers
# --------------------------------------------------------------------------------------


def _resolve_hubspot_config(
    config_data: dict | None,
    config_file: Path | str | None,
    config_dir: Optional[Path],
) -> tuple[dict, Path]:
    if config_data is not None:
        section = config_data.get("hubspot")
        if not isinstance(section, dict):
            raise ValueError("Configuration file missing 'hubspot' section")
        return section, config_dir or Path.cwd()

    data, root = load_config_data(config_file)
    section = data.get("hubspot")
    if not isinstance(section, dict):
        raise ValueError("Configuration file missing 'hubspot' section")
    return section, root


def _read_output_dir(config: Dict[str, Any], root: Path) -> Path:
    raw = config.get("output_dir", DEFAULT_OUTPUT_DIR)
    path = Path(raw)
    if not path.is_absolute():
        path = (root / path).resolve()
    return path


def _load_tables(config: Dict[str, Any], root: Path) -> List[TableConfig]:
    tables_file = config.get("tables_file", "hubspot_tables.yaml")
    path = Path(tables_file)
    if not path.is_absolute():
        path = (root / path).resolve()

    if not path.is_file():
        raise ValueError(f"HubSpot tables file not found: {path}")

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Cannot read HubSpot tables file {path}: {exc}") from exc

    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"Failed to parse HubSpot tables file {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("hubspot_tables.yaml must be a mapping with a 'tables' list")

    raw_tables = data.get("tables")
    if not isinstance(raw_tables, list) or not raw_tables:
        raise ValueError("hubspot_tables.yaml must define a non-empty 'tables' list")

    return [_parse_table_entry(entry, path) for entry in raw_tables]


def _parse_table_entry(entry: object, path: Path) -> TableConfig:
    if not isinstance(entry, dict):
        raise ValueError(f"Invalid table entry in {path}: each entry must be a mapping")

    name = _require_str(entry, "name", path)
    object_type = _require_str(entry, "object_type", path)
    fields = entry.get("fields")
    if not isinstance(fields, list) or not fields:
        raise ValueError(f"Invalid table entry in {path}: 'fields' must be a non-empty list")

    return TableConfig(
        name=name,
        object_type=object_type,
        fields=[str(f) for f in fields],
        description=entry.get("description", ""),
    )


def _require_str(entry: dict, key: str, path: Path) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"Invalid table entry in {path}: '{key}' must be a non-empty string"
        )
    return value.strip()
