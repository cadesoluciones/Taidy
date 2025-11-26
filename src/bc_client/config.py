"""Configuration helpers for Business Central client PoC."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import yaml


# ---------------------------
# Data models
# ---------------------------


@dataclass(eq=True)
class TableConfig:
    name: str
    url: str


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

REQUIRED_KEYS = [
    "BC_TENANT_ID",
    "BC_ENVIRONMENT",
    "BC_CLIENT_ID",
    "BC_CLIENT_SECRET",
    "BC_SCOPE",
    "BC_TOKEN_URL",
    "BC_COMPANY_NAME",
    "BC_OUTPUT_DIR",
]


# ---------------------------
# Public API
# ---------------------------


def load_settings(env: Optional[Iterable[tuple[str, str]]] = None) -> Settings:
    """
    Load Settings from environment variables.

    Args:
        env: Optional iterable of (key, value) pairs (useful for tests).
             If not provided, os.environ is used.

    Returns:
        A Settings object with validated configuration.
    """
    raw_env = dict(env or os.environ.items())

    _require_keys(raw_env, REQUIRED_KEYS)

    page_size = _read_page_size(raw_env)
    tables = _read_tables(raw_env)
    output_dir = _read_output_dir(raw_env)

    return Settings(
        tenant_id=raw_env["BC_TENANT_ID"],
        environment=raw_env["BC_ENVIRONMENT"],
        client_id=raw_env["BC_CLIENT_ID"],
        client_secret=raw_env["BC_CLIENT_SECRET"],
        scope=raw_env["BC_SCOPE"],
        token_url=raw_env["BC_TOKEN_URL"],
        company_id=_read_optional(raw_env, "BC_COMPANY_ID"),
        company_name=raw_env["BC_COMPANY_NAME"],
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


def _read_page_size(env: Dict[str, str]) -> int:
    raw = env.get("BC_PAGE_SIZE")
    if not raw:
        return DEFAULT_PAGE_SIZE

    try:
        page_size = int(raw)
    except ValueError as exc:
        raise ValueError("BC_PAGE_SIZE must be an integer") from exc

    if page_size <= 0:
        raise ValueError("BC_PAGE_SIZE must be greater than zero")

    return page_size


def _read_tables(env: Dict[str, str]) -> List[TableConfig]:
    tables_file = env.get("BC_TABLES_FILE", "tables.yaml")
    path = Path(tables_file).expanduser().resolve()

    if not path.is_absolute():
        raise ValueError(f"Tables file must be an absolute path: {path}")
    if not path.is_file():
        raise ValueError(f"Tables file not found or not a file: {path}")

    return _load_tables_from_file(path)


def _read_output_dir(env: Dict[str, str]) -> Path:
    path = Path(env["BC_OUTPUT_DIR"]).expanduser().resolve()

    if not path.is_absolute():
        raise ValueError(f"Output directory must be an absolute path: {path}")

    return path


def _read_optional(env: Dict[str, str], key: str) -> Optional[str]:
    value = env.get(key)
    return value.strip() if value and value.strip() else None


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

    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"Invalid table entry in {path}: missing/empty 'name'")
    if not isinstance(url, str) or not url.strip():
        raise ValueError(f"Invalid table entry in {path}: missing/empty 'url'")

    return TableConfig(name=name.strip(), url=url.strip())
