"""Configuration helpers for Business Central client PoC."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, MutableMapping, Optional

import yaml


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


REQUIRED_KEYS = {
    "BC_TENANT_ID",
    "BC_ENVIRONMENT",
    "BC_CLIENT_ID",
    "BC_CLIENT_SECRET",
    "BC_SCOPE",
    "BC_TOKEN_URL",
    "BC_COMPANY_NAME",
    "BC_OUTPUT_DIR",
}


def _env_to_dict(env: Iterable[tuple[str, str]]) -> MutableMapping[str, str]:
    result: MutableMapping[str, str] = {}
    for key, value in env:
        result[key] = value
    return result


def _load_tables_from_file(path: Path) -> List[TableConfig]:
    if not path.exists():
        raise ValueError(f"Tables file not found: {path}")

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:  # pragma: no cover - depends on yaml internals
        raise ValueError(f"Failed to parse tables file {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("Tables file must contain a mapping with a 'tables' list")

    raw_tables = data.get("tables")
    if not isinstance(raw_tables, list) or not raw_tables:
        raise ValueError("Tables file must define a non-empty 'tables' list")

    tables: List[TableConfig] = []
    for entry in raw_tables:
        if not isinstance(entry, dict):
            raise ValueError("Each table entry must be a mapping with 'name' and 'url'")
        name = entry.get("name")
        url = entry.get("url")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Table entry missing a valid 'name'")
        if not isinstance(url, str) or not url.strip():
            raise ValueError("Table entry missing a valid 'url'")
        tables.append(TableConfig(name=name.strip(), url=url.strip()))

    return tables


def load_settings(_env: Iterable[tuple[str, str]] | None = None) -> Settings:
    raw_env = _env_to_dict(_env or os.environ.items())

    missing = [key for key in REQUIRED_KEYS if key not in raw_env or not raw_env[key]]
    if missing:
        raise ValueError(
            f"Missing required configuration: {', '.join(sorted(missing))}"
        )

    page_size_raw = raw_env.get("BC_PAGE_SIZE")
    if page_size_raw:
        try:
            page_size = int(page_size_raw)
        except ValueError as exc:  # pragma: no cover - defensive branch
            raise ValueError("BC_PAGE_SIZE must be an integer") from exc
        if page_size <= 0:
            raise ValueError("BC_PAGE_SIZE must be greater than zero")
    else:
        page_size = DEFAULT_PAGE_SIZE

    tables_file = Path(raw_env.get("BC_TABLES_FILE", "tables.yaml")).expanduser()
    tables = _load_tables_from_file(tables_file)

    output_dir = Path(raw_env["BC_OUTPUT_DIR"]).expanduser()
    company_id = raw_env.get("BC_COMPANY_ID") or None

    return Settings(
        tenant_id=raw_env["BC_TENANT_ID"],
        environment=raw_env["BC_ENVIRONMENT"],
        client_id=raw_env["BC_CLIENT_ID"],
        client_secret=raw_env["BC_CLIENT_SECRET"],
        scope=raw_env["BC_SCOPE"],
        token_url=raw_env["BC_TOKEN_URL"],
        company_id=company_id,
        company_name=raw_env["BC_COMPANY_NAME"],
        tables=tables,
        page_size=page_size,
        output_dir=output_dir,
    )
