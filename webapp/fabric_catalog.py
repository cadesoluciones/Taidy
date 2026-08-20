# -*- coding: utf-8 -*-
"""
A documentation/context layer over the Fabric workspace's own structure --
NOT another way to run or manage anything already covered by
src/fabric_pipelines (that's orchestration; this is pure annotation).

Fabric itself is the source of truth for *structure* (which notebooks/
pipelines/lakehouses exist, and which folder each lives in) -- always
discovered live via FabricPipelineClient.list_items()/list_folders(), never
cached here. This module only stores the human-curated layer on top:
descriptions, ownership/governance fields, and typed relationships between
items, keyed by each item's stable Fabric id so a rename in Fabric doesn't
orphan the metadata.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from webapp.state_dir import state_path

_CATALOG_PATH = state_path("fabric_catalog.json", Path(__file__).resolve().parent)
_LOCK = threading.Lock()

RELATIONSHIP_TYPES = {"reads_from", "writes_to", "triggered_by"}
CRITICALITY_LEVELS = {"baja", "media", "alta"}
STATUS_VALUES = {"activo", "en_desuso", "deprecado"}

_EMPTY_ENTRY: dict = {
    "short_description": "",
    "long_description_markdown": "",
    "owners": [],
    "criticality": "",
    "status": "",
    "tags": [],
    "relationships": [],
    "reviewed_by": "",
    "reviewed_at": "",
}


def _read() -> Dict[str, dict]:
    if not _CATALOG_PATH.exists():
        return {}
    try:
        return json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write(data: Dict[str, dict]) -> None:
    tmp = _CATALOG_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(_CATALOG_PATH)


def get_metadata(item_id: str) -> dict:
    """Always returns a fully-shaped entry (every field present, even if
    empty) -- callers never need a None-check or a KeyError guard."""
    with _LOCK:
        entry = _read().get(item_id)
    return {**_EMPTY_ENTRY, **(entry or {})}


def list_metadata() -> Dict[str, dict]:
    with _LOCK:
        return _read()


def _clean_list(values: List[str]) -> List[str]:
    seen: List[str] = []
    for value in values:
        cleaned = value.strip()
        if cleaned and cleaned not in seen:
            seen.append(cleaned)
    return seen


def set_metadata(
    item_id: str,
    *,
    short_description: str,
    long_description_markdown: str,
    owners: List[str],
    criticality: str,
    status: str,
    tags: List[str],
    relationships: List[Dict[str, str]],
    reviewed_by: str,
) -> dict:
    for rel in relationships:
        rel_type = rel.get("type")
        target = rel.get("target_item_id")
        if rel_type not in RELATIONSHIP_TYPES:
            raise ValueError(f"Tipo de relación desconocido: {rel_type!r}")
        if not target or not isinstance(target, str):
            raise ValueError("Cada relación necesita un 'target_item_id'.")
        if target == item_id:
            raise ValueError("Un elemento no puede relacionarse consigo mismo.")

    if criticality and criticality not in CRITICALITY_LEVELS:
        raise ValueError(f"Criticidad desconocida: {criticality!r}")
    if status and status not in STATUS_VALUES:
        raise ValueError(f"Estado desconocido: {status!r}")

    entry = {
        "short_description": short_description.strip(),
        "long_description_markdown": long_description_markdown,
        "owners": _clean_list(owners),
        "criticality": criticality,
        "status": status,
        "tags": _clean_list(tags),
        "relationships": relationships,
        "reviewed_by": reviewed_by,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }
    with _LOCK:
        data = _read()
        data[item_id] = entry
        _write(data)
    return entry


def delete_metadata(item_id: str) -> None:
    """Not exposed via the API today (items are never deleted through this
    module, only through Fabric itself) -- kept for symmetry/tests and in
    case an admin ever wants to explicitly clear stale metadata."""
    with _LOCK:
        data = _read()
        if item_id in data:
            del data[item_id]
            _write(data)


def _folder_path(folder_id: Optional[str], folders_by_id: Dict[str, dict]) -> List[str]:
    path: List[str] = []
    seen = set()
    current_id = folder_id
    while current_id and current_id not in seen:
        seen.add(current_id)
        folder = folders_by_id.get(current_id)
        if folder is None:
            break
        path.append(folder.get("displayName", ""))
        current_id = folder.get("parentFolderId")
    path.reverse()
    return path


def list_catalog_items(client: Any) -> List[dict]:
    """Live Fabric items + folders, merged with locally-stored metadata.
    `client` is a FabricPipelineClient (passed in rather than constructed
    here so tests can inject a fake)."""
    items = client.list_items()
    folders = client.list_folders()
    folders_by_id = {f["id"]: f for f in folders}
    metadata = list_metadata()

    result: List[dict] = []
    for item in items:
        item_id = item.get("id", "")
        meta = {**_EMPTY_ENTRY, **metadata.get(item_id, {})}
        result.append(
            {
                "item_id": item_id,
                "name": item.get("displayName", ""),
                "type": item.get("type", ""),
                "folder_path": _folder_path(item.get("folderId"), folders_by_id),
                "short_description": meta["short_description"],
                "long_description_markdown": meta["long_description_markdown"],
                "owners": meta["owners"],
                "criticality": meta["criticality"],
                "status": meta["status"],
                "tags": meta["tags"],
                "relationships": meta["relationships"],
                "reviewed_by": meta["reviewed_by"],
                "reviewed_at": meta["reviewed_at"],
            }
        )
    return result
