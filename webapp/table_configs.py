# -*- coding: utf-8 -*-
"""
CRUD over `tables.yaml` (Business Central) and `factorial_tables.yaml`
(Factorial HR) -- the exact same data files `src/bc_client/config.py` and
`src/factorial_client/config.py` already read for real extraction runs.

BC's URLs may contain the literal placeholder `{ENVIRONMENT}` (substituted
with BC_ENVIRONMENT at extraction time, see src/bc_client/config.py) --
this module doesn't touch that substitution, it only edits the YAML *data
files* as plain dicts, same as if a person had hand-edited the file. Adding
a table here just means a new list entry becomes available the next time
someone extracts or lists tables.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.config_loader import load_config_data  # noqa: E402

_BC_TABLES_PATH = _PROJECT_ROOT / "tables.yaml"
_FACTORIAL_TABLES_PATH = _PROJECT_ROOT / "factorial_tables.yaml"
_HUBSPOT_TABLES_PATH = _PROJECT_ROOT / "hubspot_tables.yaml"


def _read(path: Path) -> List[dict]:
    if not path.is_file():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    tables = data.get("tables")
    return list(tables) if isinstance(tables, list) else []


def _write(path: Path, tables: List[dict]) -> None:
    # Writes directly into `path` rather than write-to-tmp-then-rename:
    # tables.yaml/hubspot_tables.yaml/factorial_tables.yaml are each
    # individually bind-mounted single files in production (see
    # docker-compose.yml), and os.replace()/rename() onto a bind-mounted
    # file's own path fails with "OSError: [Errno 16] Device or resource
    # busy" -- confirmed live, this broke every "add/edit/delete table"
    # action on the real deployment. Same fix already applied in
    # webapp/env_secrets.py for .env, which is bind-mounted the same way.
    path.write_text(
        yaml.dump({"tables": tables}, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )


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


def update_bc_table(
    name: str, url: str, *, description: str = "", incremental: bool = False, new_name: Optional[str] = None
) -> dict:
    url = url.strip()
    if not url:
        raise ValueError("La tabla necesita una URL de OData.")
    final_name = (new_name or name).strip()
    if not final_name:
        raise ValueError("La tabla necesita un nombre.")

    tables = _read(_BC_TABLES_PATH)
    if final_name != name and any(t.get("name") == final_name for t in tables):
        raise ValueError(f"Ya existe una tabla de Business Central llamada '{final_name}'.")

    for t in tables:
        if t.get("name") == name:
            t["name"] = final_name
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


def bc_table_fields(name: str) -> List[str]:
    """Best-effort: reads the header row of the table's last full extraction.

    Unlike Factorial/HubSpot, tables.yaml never declares a field list for a
    BC table (the URL is a whole API page whose columns are only known once
    it's actually been called) -- the sync-mapping UI needs *some* list of
    available fields to map from, and the CSV a real extraction already
    wrote is the cheapest source of truth, no live BC call required. Returns
    an empty list if the table hasn't been extracted yet.
    """
    try:
        data, root = load_config_data()
    except Exception:
        return []
    section = data.get("business_central")
    if not isinstance(section, dict):
        return []

    output_dir = Path(section.get("output_dir", "./exports"))
    if not output_dir.is_absolute():
        output_dir = (root / output_dir).resolve()

    csv_path = output_dir / "full" / f"{name}.csv"
    if not csv_path.is_file():
        return []

    with csv_path.open(encoding="utf-8", newline="") as f:
        header = next(csv.reader(f), [])
    return header


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
    new_name: Optional[str] = None,
) -> dict:
    path = path.strip()
    clean_fields = [f.strip() for f in fields if f.strip()]
    final_name = (new_name or name).strip()
    if not final_name:
        raise ValueError("La tabla necesita un nombre.")
    if not path:
        raise ValueError("La tabla necesita una ruta de la API de Factorial.")
    if not clean_fields:
        raise ValueError("Indica al menos un campo que devuelve la API.")

    tables = _read(_FACTORIAL_TABLES_PATH)
    if final_name != name and any(t.get("name") == final_name for t in tables):
        raise ValueError(f"Ya existe una tabla de Factorial llamada '{final_name}'.")

    for t in tables:
        if t.get("name") == name:
            t["name"] = final_name
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


# --------------------------------------------------------------------------------------
# HubSpot CRM (hubspot_tables.yaml: name, description, object_type, fields)
# --------------------------------------------------------------------------------------


def list_hubspot_tables_full() -> List[dict]:
    return _read(_HUBSPOT_TABLES_PATH)


def add_hubspot_table(
    name: str,
    object_type: str,
    fields: List[str],
    *,
    description: str = "",
) -> dict:
    name = name.strip()
    object_type = object_type.strip()
    clean_fields = [f.strip() for f in fields if f.strip()]
    if not name:
        raise ValueError("El objeto necesita un nombre.")
    if not object_type:
        raise ValueError("El objeto necesita un tipo de objeto de HubSpot (ej. contacts, companies, deals).")
    if not clean_fields:
        raise ValueError("Indica al menos una propiedad a extraer.")

    tables = _read(_HUBSPOT_TABLES_PATH)
    if any(t.get("name") == name for t in tables):
        raise ValueError(f"Ya existe un objeto de HubSpot llamado '{name}'.")

    entry: Dict[str, Any] = {
        "name": name,
        "description": description.strip(),
        "object_type": object_type,
        "fields": clean_fields,
    }
    tables.append(entry)
    _write(_HUBSPOT_TABLES_PATH, tables)
    return entry


def update_hubspot_table(
    name: str,
    object_type: str,
    fields: List[str],
    *,
    description: str = "",
    new_name: Optional[str] = None,
) -> dict:
    object_type = object_type.strip()
    clean_fields = [f.strip() for f in fields if f.strip()]
    final_name = (new_name or name).strip()
    if not final_name:
        raise ValueError("El objeto necesita un nombre.")
    if not object_type:
        raise ValueError("El objeto necesita un tipo de objeto de HubSpot (ej. contacts, companies, deals).")
    if not clean_fields:
        raise ValueError("Indica al menos una propiedad a extraer.")

    tables = _read(_HUBSPOT_TABLES_PATH)
    if final_name != name and any(t.get("name") == final_name for t in tables):
        raise ValueError(f"Ya existe un objeto de HubSpot llamado '{final_name}'.")

    for t in tables:
        if t.get("name") == name:
            t["name"] = final_name
            t["object_type"] = object_type
            t["description"] = description.strip()
            t["fields"] = clean_fields
            _write(_HUBSPOT_TABLES_PATH, tables)
            return t
    raise ValueError(f"No existe un objeto de HubSpot llamado '{name}'.")


def delete_hubspot_table(name: str) -> None:
    tables = _read(_HUBSPOT_TABLES_PATH)
    remaining = [t for t in tables if t.get("name") != name]
    _write(_HUBSPOT_TABLES_PATH, remaining)
