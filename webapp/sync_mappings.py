# -*- coding: utf-8 -*-
"""
CRUD over sync_mappings.yaml -- field-level mappings used to reconcile
records between two already-configured tables (e.g. Business Central's
bc_contact and HubSpot's hubspot_contacts), matched by a business key
(e.g. email) rather than by full-row identity like Factorial's incremental
merge does. `date_field` names the "last modified" column on each side --
whichever side has the more recent value wins a conflict (see
src/sync_engine/compare.py).

This module only edits the YAML data file, same discipline as
table_configs.py: the actual sync engine that reads/writes real BC/HubSpot
records (a later phase) is a separate module that reads this same file.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_SYNC_MAPPINGS_PATH = _PROJECT_ROOT / "sync_mappings.yaml"

VALID_SYSTEMS = {"business_central", "factorial", "hubspot"}


def _read() -> List[dict]:
    if not _SYNC_MAPPINGS_PATH.is_file():
        return []
    data = yaml.safe_load(_SYNC_MAPPINGS_PATH.read_text(encoding="utf-8")) or {}
    mappings = data.get("mappings")
    return list(mappings) if isinstance(mappings, list) else []


def _write(mappings: List[dict]) -> None:
    tmp = _SYNC_MAPPINGS_PATH.with_suffix(".tmp")
    tmp.write_text(
        yaml.dump({"mappings": mappings}, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    tmp.replace(_SYNC_MAPPINGS_PATH)


def list_mappings_full() -> List[dict]:
    return _read()


def _validate_system_ref(ref: dict, label: str) -> Dict[str, str]:
    if not isinstance(ref, dict):
        raise ValueError(f"'{label}' debe indicar sistema y tabla.")
    system = str(ref.get("system", "")).strip()
    table = str(ref.get("table", "")).strip()
    if system not in VALID_SYSTEMS:
        raise ValueError(f"'{label}.system' debe ser uno de: {', '.join(sorted(VALID_SYSTEMS))}.")
    if not table:
        raise ValueError(f"'{label}.table' no puede estar vacío.")
    return {"system": system, "table": table}


def _validate_field_pair(pair: dict, label: str) -> Dict[str, str]:
    if not isinstance(pair, dict):
        raise ValueError(f"'{label}' debe indicar 'source' y 'target'.")
    source = str(pair.get("source", "")).strip()
    target = str(pair.get("target", "")).strip()
    if not source or not target:
        raise ValueError(f"'{label}' necesita tanto el campo de origen como el de destino.")
    return {"source": source, "target": target}


def _validate_row_filter(row_filter: Optional[dict], label: str) -> Optional[Dict[str, str]]:
    """An optional 'only include rows where field == value' restriction on
    one side of a mapping -- e.g. Business Central's shared bc_contact table
    holds both Person and Company records, and only one of them belongs in
    a given HubSpot object (contacts vs companies). None means no
    restriction (today's behavior for every existing mapping)."""
    if row_filter is None:
        return None
    if not isinstance(row_filter, dict):
        raise ValueError(f"'{label}' debe indicar 'field' y 'equals'.")
    field = str(row_filter.get("field", "")).strip()
    equals = str(row_filter.get("equals", "")).strip()
    if not field or not equals:
        raise ValueError(f"'{label}' necesita tanto el campo como el valor.")
    return {"field": field, "equals": equals}


def _validate_fields(fields: List[dict]) -> List[Dict[str, str]]:
    if not isinstance(fields, list) or not fields:
        raise ValueError("Indica al menos un par de campos a sincronizar.")
    clean = [_validate_field_pair(f, "fields") for f in fields]
    sources = [f["source"] for f in clean]
    if len(sources) != len(set(sources)):
        raise ValueError("Un mismo campo de origen no puede mapearse dos veces.")
    return clean


def add_mapping(
    name: str,
    source: dict,
    target: dict,
    matching_key: dict,
    date_field: dict,
    fields: List[dict],
    *,
    description: str = "",
    source_filter: Optional[dict] = None,
    target_filter: Optional[dict] = None,
) -> dict:
    name = name.strip()
    if not name:
        raise ValueError("El mapeo necesita un nombre.")

    mappings = _read()
    if any(m.get("name") == name for m in mappings):
        raise ValueError(f"Ya existe un mapeo llamado '{name}'.")

    entry: Dict[str, Any] = {
        "name": name,
        "description": description.strip(),
        "source": _validate_system_ref(source, "source"),
        "target": _validate_system_ref(target, "target"),
        "matching_key": _validate_field_pair(matching_key, "matching_key"),
        "date_field": _validate_field_pair(date_field, "date_field"),
        "fields": _validate_fields(fields),
        "source_filter": _validate_row_filter(source_filter, "source_filter"),
        "target_filter": _validate_row_filter(target_filter, "target_filter"),
    }
    mappings.append(entry)
    _write(mappings)
    return entry


def update_mapping(
    name: str,
    source: dict,
    target: dict,
    matching_key: dict,
    date_field: dict,
    fields: List[dict],
    *,
    description: str = "",
    source_filter: Optional[dict] = None,
    target_filter: Optional[dict] = None,
    new_name: Optional[str] = None,
) -> dict:
    final_name = (new_name or name).strip()
    if not final_name:
        raise ValueError("El mapeo necesita un nombre.")

    mappings = _read()
    if final_name != name and any(m.get("name") == final_name for m in mappings):
        raise ValueError(f"Ya existe un mapeo llamado '{final_name}'.")

    for m in mappings:
        if m.get("name") == name:
            m["name"] = final_name
            m["description"] = description.strip()
            m["source"] = _validate_system_ref(source, "source")
            m["target"] = _validate_system_ref(target, "target")
            m["matching_key"] = _validate_field_pair(matching_key, "matching_key")
            m["date_field"] = _validate_field_pair(date_field, "date_field")
            m["fields"] = _validate_fields(fields)
            m["source_filter"] = _validate_row_filter(source_filter, "source_filter")
            m["target_filter"] = _validate_row_filter(target_filter, "target_filter")
            _write(mappings)
            return m
    raise ValueError(f"No existe un mapeo llamado '{name}'.")


def delete_mapping(name: str) -> None:
    mappings = _read()
    remaining = [m for m in mappings if m.get("name") != name]
    _write(remaining)


def reorder_mappings(ordered_names: List[str]) -> List[dict]:
    """Persists a new display order for the mappings list -- purely cosmetic
    (list order); compare/apply always look a mapping up by name."""
    mappings = _read()
    by_name = {m["name"]: m for m in mappings}
    if set(ordered_names) != set(by_name):
        raise ValueError("La lista de mapeos a reordenar no coincide con los mapeos existentes.")
    reordered = [by_name[name] for name in ordered_names]
    _write(reordered)
    return reordered
