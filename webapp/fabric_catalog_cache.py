# -*- coding: utf-8 -*-
"""
Local cache of the last successfully-seen Fabric-discovered catalog items --
plain Fabric workspace items (Lakehouse, Notebook, DataPipeline, Report,
SemanticModel, ...) and each Lakehouse's own tables. Structure is normally
always read live (see webapp/fabric_catalog.py's list_catalog_items()), but
that means anything Fabric stops returning -- a real outage, expired
credentials, or (confirmed live 2026-09-01) a workspace whose Fabric
capacity/license lapsed, where the API answers 200 but silently stops
listing non-Power-BI item types -- used to vanish from the catalog without a
trace. This stores just enough of each item's own facts (name/type/folder
path -- NOT governance metadata, that already lives reliably in
fabric_catalog.json and is re-merged on every read) to keep showing it,
flagged "sin conexión", until it's either seen live again or explicitly
removed via delete_entry().

BC/HubSpot/Factorial/custom items never touch this cache -- they're never
live-discovered in the first place, so there's nothing about them that can
go stale or disappear.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from webapp.state_dir import state_path

_CACHE_PATH = state_path("fabric_catalog_live_cache.json", Path(__file__).resolve().parent)
_LOCK = threading.Lock()


def _read() -> Dict[str, dict]:
    if not _CACHE_PATH.exists():
        return {}
    try:
        return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write(data: Dict[str, dict]) -> None:
    tmp = _CACHE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(_CACHE_PATH)


def merge_and_get(live_facts: Dict[str, dict]) -> Dict[str, dict]:
    """Upserts every item just confirmed live (fresh name/type/folder_path
    + now() as last_synced_at) into the cache; anything cached from an
    earlier sync that isn't in `live_facts` this time is left untouched --
    still returned, just with its old last_synced_at, which is exactly what
    lets a caller tell "online" (present in live_facts) apart from "offline"
    (only here). An empty `live_facts` (Fabric totally unreachable this
    round) still returns the full existing cache, unchanged -- the natural
    "serve everything from cache" fallback."""
    now = datetime.now(timezone.utc).isoformat()
    with _LOCK:
        data = _read()
        for item_id, facts in live_facts.items():
            data[item_id] = {**facts, "last_synced_at": now}
        _write(data)
        return data


def delete_entry(item_id: str) -> None:
    """Forgets an item's cached copy -- if the real item still exists in
    Fabric and is seen live again later, it simply reappears then; this
    only ever touches the local cache, never Fabric itself."""
    with _LOCK:
        data = _read()
        if item_id in data:
            del data[item_id]
            _write(data)


def list_cached_ids() -> List[str]:
    with _LOCK:
        return list(_read().keys())
