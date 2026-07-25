# -*- coding: utf-8 -*-
"""
CRUD over `tables.yaml` (Business Central) and `factorial_tables.yaml`
(Factorial HR) -- the exact same data files `src/bc_client/config.py` and
`src/factorial_client/config.py` already read for real extraction runs.

This module only edits the YAML *data files*; it never touches src/**'s
parsing/validation logic. Adding a table here just means a new list entry
becomes available the next time someone extracts or lists tables -- the
same as if a person had hand-edited the YAML file.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_BC_TABLES_PATH = _PROJECT_ROOT / "tables.yaml"
_FACTORIAL_TABLES_PATH = _PROJECT_ROOT / "factorial_tables.yaml"


def _read(path: Path) -> List[dict]:
    if not path.is_file():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    tables = data.get("tables")
    return list(tables) if isinstance(tables, list) else []


def _write(path: Path, tables: List[dict]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        yaml.dump({"tables": tables}, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    tmp.replace(path)


# --------------------------------------------------------------------------------------
# Business Central (tables.yaml: name, description, url, incremental)
# --------------------------------------------------------------------------------------


def list_bc_tables_full() -> List[dict]:
    return _read(_BC_TABLES_PATH)


def add_bc_table(name: str, url: str, *, description: str = "", incremental: bool = False) -> dict:
    name = name.strip()
    url = url.strip()
    if not name:
        raise ValueError("La tabla necesita un nombre.")
    if not url:
        raise ValueError("La tabla necesita una URL de OData.")

    tables = _read(_BC_TABLES_PATH)
    if any(t.get("name") == name for t in tables):
        raise ValueError(f"Ya existe una tabla de Business Central llamada '{name}'.")

    entry = {"name": name, "description": description.strip(), "url": url, "incremental": bool(incremental)}
    tables.append(entry)
    _write(_BC_TABLES_PATH, tables)
    return entry


def update_bc_table(name: str, url: str, *, description: str = "", incremental: bool = False) -> dict:
    url = url.strip()
    if not url:
        raise ValueError("La tabla necesita una URL de OData.")

    tables = _read(_BC_TABLES_PATH)
    for t in tables:
        if t.get("name") == name:
            t["url"] = url
            t["description"] = description.strip()
            t["incremental"] = bool(incremental)
            _write(_BC_TABLES_PATH, tables)
            return t
    raise ValueError(f"No existe una tabla de Business Central llamada '{name}'.")


def delete_bc_table(name: str) -> None:
    tables = _read(_BC_TABLES_PATH)
    remaining = [t for t in tables if t.get("name") != name]
    _write(_BC_TABLES_PATH, remaining)


# --------------------------------------------------------------------------------------
# Factorial HR (factorial_tables.yaml: name, description, path, fields, date_range,
# employee_filter, incremental, overlap_days, chunk_days)
# --------------------------------------------------------------------------------------


def list_factorial_tables_full() -> List[dict]:
    return _read(_FACTORIAL_TABLES_PATH)


def add_factorial_table(
    name: str,
    path: str,
    fields: List[str],
    *,
    description: str = "",
    date_range: bool = True,
    employee_filter: bool = True,
    incremental: bool = False,
    overlap_days: Optional[int] = None,
    chunk_days: Optional[int] = None,
) -> dict:
    name = name.strip()
    path = path.strip()
    clean_fields = [f.strip() for f in fields if f.strip()]
    if not name:
        raise ValueError("La tabla necesita un nombre.")
    if not path:
        raise ValueError("La tabla necesita una ruta de la API de Factorial.")
    if not clean_fields:
        raise ValueError("Indica al menos un campo que devuelve la API.")

    tables = _read(_FACTORIAL_TABLES_PATH)
    if any(t.get("name") == name for t in tables):
        raise ValueError(f"Ya existe una tabla de Factorial llamada '{name}'.")

    entry: Dict[str, Any] = {
        "name": name,
        "description": description.strip(),
        "path": path,
        "date_range": bool(date_range),
        "employee_filter": bool(employee_filter),
        "incremental": bool(incremental),
        "fields": clean_fields,
    }
    if overlap_days is not None:
        entry["overlap_days"] = int(overlap_days)
    if chunk_days is not None:
        entry["chunk_days"] = int(chunk_days)

    tables.append(entry)
    _write(_FACTORIAL_TABLES_PATH, tables)
    return entry


def update_factorial_table(
    name: str,
    path: str,
    fields: List[str],
    *,
    description: str = "",
    date_range: bool = True,
    employee_filter: bool = True,
    incremental: bool = False,
    overlap_days: Optional[int] = None,
    chunk_days: Optional[int] = None,
) -> dict:
    path = path.strip()
    clean_fields = [f.strip() for f in fields if f.strip()]
    if not path:
        raise ValueError("La tabla necesita una ruta de la API de Factorial.")
    if not clean_fields:
        raise ValueError("Indica al menos un campo que devuelve la API.")

    tables = _read(_FACTORIAL_TABLES_PATH)
    for t in tables:
        if t.get("name") == name:
            t["path"] = path
            t["description"] = description.strip()
            t["date_range"] = bool(date_range)
            t["employee_filter"] = bool(employee_filter)
            t["incremental"] = bool(incremental)
            t["fields"] = clean_fields
            t.pop("overlap_days", None)
            t.pop("chunk_days", None)
            if overlap_days is not None:
                t["overlap_days"] = int(overlap_days)
            if chunk_days is not None:
                t["chunk_days"] = int(chunk_days)
            _write(_FACTORIAL_TABLES_PATH, tables)
            return t
    raise ValueError(f"No existe una tabla de Factorial llamada '{name}'.")


def delete_factorial_table(name: str) -> None:
    tables = _read(_FACTORIAL_TABLES_PATH)
    remaining = [t for t in tables if t.get("name") != name]
    _write(_FACTORIAL_TABLES_PATH, remaining)
