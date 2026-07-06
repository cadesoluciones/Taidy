# -*- coding: utf-8 -*-
"""
Configuration loading for the Factorial HR client.

Reads FACTORIAL_API_KEY and VERSION_API_FACTORIAL from environment variables.
Table definitions are loaded from the YAML file referenced in config.json.
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

FACTORIAL_BASE_URL = "https://api.factorialhr.com/api"

REQUIRED_ENV_KEYS = ["FACTORIAL_API_KEY", "VERSION_API_FACTORIAL"]

DEFAULT_OVERLAP_DAYS = 2


# --------------------------------------------------------------------------------------
# Data Models
# --------------------------------------------------------------------------------------


@dataclass
class TableConfig:
    """Represents a single Factorial API endpoint to fetch."""

    name: str
    path: str
    fields: List[str]
    description: str = ""
    version: Optional[str] = None        # overrides Settings.api_version if set
    date_range: bool = True              # whether to send start_on / end_on
    employee_filter: bool = True         # whether to send employee_ids[]
    incremental: bool = False            # whether to use checkpoint-based extraction
    overlap_days: Optional[int] = None   # overrides Settings.overlap_days if set
    extra_params: List[tuple] = None     # static extra query params from YAML
    chunk_days: Optional[int] = None     # split date range into windows of this size


DEFAULT_OUTPUT_DIR = "./exports_factorial"


@dataclass
class Settings:
    """All settings required to call the Factorial HR API."""

    api_key: str
    api_version: str
    tables: List[TableConfig]
    base_url: str = FACTORIAL_BASE_URL
    output_dir: Path = None  # resolved in load_settings
    overlap_days: int = DEFAULT_OVERLAP_DAYS


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
    Loads Factorial settings from environment variables and config files.

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

    config_section, config_root = _resolve_factorial_config(
        config_data, config_file, config_dir
    )

    tables = _load_tables(config_section, config_root)

    output_dir = _read_output_dir(config_section, config_root)
    overlap_days = _read_overlap_days(raw_env)

    return Settings(
        api_key=raw_env["FACTORIAL_API_KEY"],
        api_version=raw_env["VERSION_API_FACTORIAL"],
        base_url=config_section.get("base_url", FACTORIAL_BASE_URL),
        tables=tables,
        output_dir=output_dir,
        overlap_days=overlap_days,
    )


# --------------------------------------------------------------------------------------
# Internal helpers
# --------------------------------------------------------------------------------------


def _resolve_factorial_config(
    config_data: dict | None,
    config_file: Path | str | None,
    config_dir: Optional[Path],
) -> tuple[dict, Path]:
    if config_data is not None:
        section = config_data.get("factorial")
        if not isinstance(section, dict):
            raise ValueError("Configuration file missing 'factorial' section")
        return section, config_dir or Path.cwd()

    data, root = load_config_data(config_file)
    section = data.get("factorial")
    if not isinstance(section, dict):
        raise ValueError("Configuration file missing 'factorial' section")
    return section, root


def _read_overlap_days(env: Dict[str, str]) -> int:
    raw = env.get("FACTORIAL_OVERLAP_DAYS", str(DEFAULT_OVERLAP_DAYS))
    try:
        value = int(raw)
    except (ValueError, TypeError) as exc:
        raise ValueError("FACTORIAL_OVERLAP_DAYS must be an integer") from exc
    if value < 0:
        raise ValueError("FACTORIAL_OVERLAP_DAYS must be >= 0")
    return value


def _read_output_dir(config: Dict[str, Any], root: Path) -> Path:
    raw = config.get("output_dir", DEFAULT_OUTPUT_DIR)
    path = Path(raw)
    if not path.is_absolute():
        path = (root / path).resolve()
    return path


def _load_tables(config: Dict[str, Any], root: Path) -> List[TableConfig]:
    tables_file = config.get("tables_file", "factorial_tables.yaml")
    path = Path(tables_file)
    if not path.is_absolute():
        path = (root / path).resolve()

    if not path.is_file():
        raise ValueError(f"Factorial tables file not found: {path}")

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Cannot read factorial tables file {path}: {exc}") from exc

    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"Failed to parse factorial tables file {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("factorial_tables.yaml must be a mapping with a 'tables' list")

    raw_tables = data.get("tables")
    if not isinstance(raw_tables, list) or not raw_tables:
        raise ValueError("factorial_tables.yaml must define a non-empty 'tables' list")

    return [_parse_table_entry(entry, path) for entry in raw_tables]


def _parse_table_entry(entry: object, path: Path) -> TableConfig:
    if not isinstance(entry, dict):
        raise ValueError(f"Invalid table entry in {path}: each entry must be a mapping")

    name = _require_str(entry, "name", path)
    table_path = _require_str(entry, "path", path)
    fields = entry.get("fields")
    if not isinstance(fields, list) or not fields:
        raise ValueError(f"Invalid table entry in {path}: 'fields' must be a non-empty list")

    raw_overlap = entry.get("overlap_days")
    overlap_days: Optional[int] = None
    if raw_overlap is not None:
        try:
            overlap_days = int(raw_overlap)
        except (ValueError, TypeError) as exc:
            raise ValueError(
                f"Invalid table entry in {path}: 'overlap_days' must be an integer"
            ) from exc
        if overlap_days < 0:
            raise ValueError(
                f"Invalid table entry in {path}: 'overlap_days' must be >= 0"
            )

    raw_extra = entry.get("extra_params") or []
    if not isinstance(raw_extra, list):
        raise ValueError(f"Invalid table entry in {path}: 'extra_params' must be a list")
    extra_params = [(str(p[0]), str(p[1])) for p in raw_extra if len(p) == 2]

    raw_chunk = entry.get("chunk_days")
    chunk_days: Optional[int] = None
    if raw_chunk is not None:
        try:
            chunk_days = int(raw_chunk)
        except (ValueError, TypeError) as exc:
            raise ValueError(
                f"Invalid table entry in {path}: 'chunk_days' must be an integer"
            ) from exc
        if chunk_days <= 0:
            raise ValueError(f"Invalid table entry in {path}: 'chunk_days' must be > 0")

    return TableConfig(
        name=name,
        path=table_path,
        fields=[str(f) for f in fields],
        description=entry.get("description", ""),
        version=entry.get("version") or None,
        date_range=bool(entry.get("date_range", True)),
        employee_filter=bool(entry.get("employee_filter", True)),
        incremental=bool(entry.get("incremental", False)),
        overlap_days=overlap_days,
        extra_params=extra_params,
        chunk_days=chunk_days,
    )


def _require_str(entry: dict, key: str, path: Path) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"Invalid table entry in {path}: '{key}' must be a non-empty string"
        )
    return value.strip()
