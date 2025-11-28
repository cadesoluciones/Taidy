"""Configuration helpers for Business Central client PoC."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml

from src.config_loader import load_config_data


# ---------------------------
# Data models
# ---------------------------


@dataclass(eq=True)
class TableConfig:
    name: str
    url: str
    incremental: bool = False


@dataclass
class Settings:
    tenant_id: str
    environment: str
    client_id: str
    client_secret: str
    scope: str
    token_url: str
    company_id: Optional[str]
    company_name: str
    tables: List[TableConfig]
    page_size: int
    output_dir: Path


DEFAULT_PAGE_SIZE = 1000

REQUIRED_SECRET_KEYS = ["BC_CLIENT_SECRET"]


# ---------------------------
# Public API
# ---------------------------


def load_settings(
    env: Optional[Iterable[tuple[str, str]]] = None,
    *,
    config_data: dict | None = None,
    config_file: Path | str | None = None,
    config_dir: Optional[Path] = None,
) -> Settings:
    """
    Load Settings from environment variables.

    Args:
        env: Optional iterable of (key, value) pairs (useful for tests).
             If not provided, os.environ is used.

    Returns:
        A Settings object with validated configuration.
    """
    raw_env = dict(env or os.environ.items())
    _require_keys(raw_env, REQUIRED_SECRET_KEYS)

    config_section, config_root = _resolve_business_central_config(
        config_data, config_file, config_dir
    )

    page_size = _read_page_size(config_section)
    tables = _read_tables(config_section, config_root)
    output_dir = _read_output_dir(config_section, config_root)

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


# ---------------------------
# Validation / parsing helpers
# ---------------------------


def _require_keys(env: Dict[str, str], keys: List[str]) -> None:
    missing = [k for k in keys if not env.get(k)]
    if missing:
        missing_str = ", ".join(sorted(missing))
        raise ValueError(f"Missing required configuration: {missing_str}")


def _read_page_size(config: Dict[str, Any]) -> int:
    raw = config.get("page_size")
    if raw is None:
        return DEFAULT_PAGE_SIZE

    try:
        page_size = int(raw)
    except ValueError as exc:
        raise ValueError("BC_PAGE_SIZE must be an integer") from exc

    if page_size <= 0:
        raise ValueError("BC_PAGE_SIZE must be greater than zero")

    return page_size


def _read_tables(config: Dict[str, str], root: Path) -> List[TableConfig]:
    tables_file = config.get("tables_file", "tables.yaml")
    path = Path(tables_file)
    if not path.is_absolute():
        path = (root / path).resolve()

    if not path.is_absolute():
        raise ValueError(f"Tables file must be an absolute path: {path}")
    if not path.is_file():
        raise ValueError(f"Tables file not found or not a file: {path}")

    return _load_tables_from_file(path)


def _read_output_dir(config: Dict[str, str], root: Path) -> Path:
    path = Path(config["output_dir"])
    if not path.is_absolute():
        path = (root / path).resolve()

    if not path.is_absolute():
        raise ValueError(f"Output directory must be an absolute path: {path}")

    return path


def _load_tables_from_file(path: Path) -> List[TableConfig]:
    data = _read_yaml(path)

    if not isinstance(data, dict):
        raise ValueError("Tables file must be a mapping with a 'tables' list")

    raw_tables = data.get("tables")
    if not isinstance(raw_tables, list) or not raw_tables:
        raise ValueError("Tables file must define a non-empty 'tables' list")

    tables: List[TableConfig] = []
    for entry in raw_tables:
        tables.append(_parse_table_entry(entry, path))

    return tables


def _read_yaml(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Failed to read tables file {path}: {exc}") from exc

    try:
        return yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:  # pragma: no cover
        raise ValueError(f"Failed to parse tables file {path}: {exc}") from exc


def _parse_table_entry(entry: object, path: Path) -> TableConfig:
    if not isinstance(entry, dict):
        raise ValueError(f"Invalid table entry in {path}: each entry must be a mapping")

    name = entry.get("name")
    url = entry.get("url")
    incremental = bool(entry.get("incremental", False))

    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"Invalid table entry in {path}: missing/empty 'name'")
    if not isinstance(url, str) or not url.strip():
        raise ValueError(f"Invalid table entry in {path}: missing/empty 'url'")

    return TableConfig(
        name=name.strip(),
        url=url.strip(),
        incremental=incremental,
    )


def _resolve_business_central_config(
    config_data: dict | None,
    config_file: Path | str | None,
    config_dir: Optional[Path],
) -> tuple[dict, Path]:
    if config_data is not None:
        section = config_data.get("business_central")
        if not isinstance(section, dict):
            raise ValueError("Configuration file missing 'business_central' section")
        return section, config_dir or Path.cwd()

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
) -> Optional[str]:
    if value is None:
        if required:
            raise ValueError(f"Invalid table entry in {path}: missing '{field_name}'")
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"Invalid table entry in {path}: field '{field_name}' must be a non-empty string"
        )
    return value.strip()
