# -*- coding: utf-8 -*-
"""
Configuration loading, validation, and data models for the Business Central client.

This module is responsible for consolidating settings from configuration files
(like `config.json` and `tables.yaml`) and environment variables into a single,
type-safe `Settings` object. It performs validation to ensure that all required
configuration is present and well-formed before the application attempts to
make API calls.
"""

# --------------------------------------------------------------------------------------
# Imports
# --------------------------------------------------------------------------------------

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml

from src.config_loader import load_config_data

# --------------------------------------------------------------------------------------
# Data Models
# --------------------------------------------------------------------------------------


@dataclass(eq=True)
class TableConfig:
    """
    Represents the configuration for a single table to be extracted.

    Attributes:
        name: The unique, human-readable name for the table (e.g., "Customers").
        url: The full OData URL for fetching the table data.
        incremental: A flag indicating if the table supports incremental extraction
                     using a watermark. Defaults to False.
    """

    name: str
    url: str
    incremental: bool = False


@dataclass
class Settings:
    """
    A container for all Business Central client settings.

    This object centralizes all configuration required for authentication, API
    requests, and data export, providing a single source of truth for the rest of
    the application.
    """

    # --- Authentication and API details ---
    tenant_id: str
    environment: str
    client_id: str
    client_secret: str
    scope: str
    token_url: str

    # --- Business Central specific details ---
    company_id: Optional[str]
    company_name: str

    # --- Extraction settings ---
    tables: List[TableConfig]
    page_size: int
    output_dir: Path


# --------------------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------------------

# DEFAULT_PAGE_SIZE is used if no page size is specified in the config.
DEFAULT_PAGE_SIZE = 1000

# REQUIRED_SECRET_KEYS lists environment variables that must be set for the
# application to run. These are secrets and are not stored in config files.
REQUIRED_SECRET_KEYS = ["BC_CLIENT_SECRET"]


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
    Loads and validates all Business Central settings from various sources.

    This is the main entry point for configuration loading. It orchestrates the
    reading of environment variables and the `business_central` section of the
    JSON config file, then populates a `Settings` object.

    Args:
        env: An optional iterable of (key, value) pairs for environment
             variables, primarily for testing. Defaults to `os.environ`.
        config_data: Optional pre-loaded config data, for testing.
        config_file: Optional path to the main JSON config file.
        config_dir: Optional path to the directory of the config file.

    Returns:
        A fully validated and populated `Settings` object.
    """
    # Load environment variables, prioritizing the `env` argument for tests.
    raw_env = dict(env or os.environ.items())
    _require_keys(raw_env, REQUIRED_SECRET_KEYS)

    # Load the 'business_central' section from the main JSON config.
    config_section, config_root = _resolve_business_central_config(
        config_data, config_file, config_dir
    )

    # Parse individual settings from the config section.
    page_size = _read_page_size(config_section)
    tables = _read_tables(config_section, config_root)
    output_dir = _read_output_dir(config_section, config_root)

    # Construct the final, immutable Settings object.
    return Settings(
        tenant_id=config_section["tenant_id"],
        environment=config_section["environment"],
        client_id=config_section["client_id"],
        client_secret=raw_env["BC_CLIENT_SECRET"],
        scope=config_section["scope"],
        token_url=config_section["token_url"],
        company_id=config_section.get("company_id"),
        company_name=config_section["company_name"],
        tables=tables,
        page_size=page_size,
        output_dir=output_dir,
    )


# --------------------------------------------------------------------------------------
# Internal Validation and Parsing Helpers
# --------------------------------------------------------------------------------------


def _require_keys(env: Dict[str, str], keys: List[str]) -> None:
    """
    Ensures that all required secret keys are present in the environment.

    Args:
        env: A dictionary representing the environment variables.
        keys: A list of keys that must be present.

    Raises:
        ValueError: If any of the specified keys are missing or empty.
    """
    missing = [k for k in keys if not env.get(k)]
    if missing:
        missing_str = ", ".join(sorted(missing))
        raise ValueError(f"Missing required configuration: {missing_str}")


def _read_page_size(config: Dict[str, Any]) -> int:
    """
    Parses the page size from the config, with validation.
    """
    raw = config.get("page_size")
    if raw is None:
        return DEFAULT_PAGE_SIZE

    try:
        page_size = int(raw)
    except (ValueError, TypeError) as exc:
        raise ValueError("BC_PAGE_SIZE must be an integer") from exc

    if page_size <= 0:
        raise ValueError("BC_PAGE_SIZE must be greater than zero")

    return page_size


def _read_tables(config: Dict[str, str], root: Path) -> List[TableConfig]:
    """
    Loads table configurations from the specified YAML file.

    Resolves the path to the tables file relative to the main config's
    directory (`root`) if it's not absolute.

    Args:
        config: The `business_central` config section.
        root: The parent directory of the main `config.json`.

    Returns:
        A list of `TableConfig` objects.
    """
    tables_file = config.get("tables_file", "tables.yaml")
    path = Path(tables_file)
    if not path.is_absolute():
        path = (root / path).resolve()

    if not path.is_file():
        raise ValueError(f"Tables file not found or not a file: {path}")

    return _load_tables_from_file(path)


def _read_output_dir(config: Dict[str, str], root: Path) -> Path:
    """
    Resolves and validates the output directory path.
    """
    path = Path(config["output_dir"])
    if not path.is_absolute():
        path = (root / path).resolve()

    return path


def _load_tables_from_file(path: Path) -> List[TableConfig]:
    """
    Parses a list of TableConfig objects from a YAML file.

    Args:
        path: The absolute path to the YAML file.

    Returns:
        A list of `TableConfig` objects.
    """
    data = _read_yaml(path)

    if not isinstance(data, dict):
        raise ValueError("Tables file must be a mapping with a 'tables' list")

    raw_tables = data.get("tables")
    if not isinstance(raw_tables, list) or not raw_tables:
        raise ValueError("Tables file must define a non-empty 'tables' list")

    if "base_api_url" in data:
        raise ValueError(
            f"Invalid tables file {path}: top-level 'base_api_url' is not supported; "
            "each table entry must define a full 'url'"
        )

    tables: List[TableConfig] = []
    for entry in raw_tables:
        tables.append(_parse_table_entry(entry, path))

    return tables


def _read_yaml(path: Path) -> dict:
    """
    Reads and safely parses a YAML file.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Failed to read tables file {path}: {exc}") from exc

    try:
        # `safe_load` is used to prevent arbitrary code execution from YAML.
        return yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:  # pragma: no cover
        raise ValueError(f"Failed to parse tables file {path}: {exc}") from exc


def _parse_table_entry(entry: object, path: Path) -> TableConfig:
    """
    Parses a single dictionary from the YAML file into a `TableConfig` object.

    Args:
        entry: A dictionary representing a table.
        path: The path to the YAML file, for use in error messages.

    Returns:
        A validated `TableConfig` object.
    """
    if not isinstance(entry, dict):
        raise ValueError(f"Invalid table entry in {path}: each entry must be a mapping")

    # Use `_clean_str` for consistent validation and error messages.
    name = _clean_str(entry.get("name"), path, "name")
    if "api_path" in entry:
        raise ValueError(
            f"Invalid table entry in {path}: 'api_path' is not supported; use full 'url'"
        )
    url = _clean_str(entry.get("url"), path, "url")
    incremental = bool(entry.get("incremental", False))

    return TableConfig(name=name, url=url, incremental=incremental)


def _resolve_business_central_config(
    config_data: dict | None,
    config_file: Path | str | None,
    config_dir: Optional[Path],
) -> tuple[dict, Path]:
    """
    Helper to load the main JSON config and extract the 'business_central' section.
    """
    if config_data is not None:
        # If config is passed directly (for tests), use it.
        section = config_data.get("business_central")
        if not isinstance(section, dict):
            raise ValueError("Configuration file missing 'business_central' section")
        return section, config_dir or Path.cwd()

    # Otherwise, load it from disk.
    data, root = load_config_data(config_file)
    section = data.get("business_central")
    if not isinstance(section, dict):
        raise ValueError("Configuration file missing 'business_central' section")
    return section, root


def _clean_str(
    value: Optional[object],
    path: Path,
    field_name: str,
    *,
    required: bool = True,
) -> str:
    """
    Validates that a value is a non-empty string.

    Args:
        value: The value to check.
        path: The file path, for inclusion in error messages.
        field_name: The name of the field being checked.
        required: If True, `None` values will raise an error.

    Returns:
        The cleaned, stripped string.
    """
    if value is None:
        if required:
            raise ValueError(f"Invalid table entry in {path}: missing '{field_name}'")
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"Invalid table entry in {path}: field '{field_name}' must be a non-empty string"
        )
    return value.strip()
