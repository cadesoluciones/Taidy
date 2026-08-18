# -*- coding: utf-8 -*-
"""
Persisted per-mapping-side cache for the sync comparison engine's incremental
fetch (src/sync_engine/compare.py) -- one JSON file per (mapping name,
source/target side), storing the last known full row set by matching-key,
plus enough metadata to decide when a full refresh is needed instead of a
delta fetch.

Why this exists: compare_mapping()'s create/delete detection is a full
key-set diff between both sides (see compare.py's _index_by_key). An
incremental "what changed since X" fetch alone can't tell "unchanged" apart
from "no longer exists on this side at all" -- so every incremental fetch is
merged on top of this cache to keep feeding compare_mapping() the same
logically-complete row set it always had, just without re-fetching rows
that haven't changed since last time.

Deletions are still invisible to a pure incremental fetch (neither BC nor
HubSpot exposes them as a "change"), so `is_stale()` also forces a full
refresh periodically (see DEFAULT_MAX_AGE_HOURS) -- this bounds how stale
"record no longer exists" detection can get, rather than never catching it.
"""

from __future__ import annotations

import json
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.utils.paths import table_filename  # noqa: E402
from webapp.state_dir import state_path  # noqa: E402

_DEFAULT_DIR = Path(__file__).resolve().parent
_LOCK = threading.Lock()

# Force a full refresh at least this often, regardless of watermark
# freshness -- see module docstring on why deletions need this.
DEFAULT_MAX_AGE_HOURS = 24


@dataclass
class MappingSideCache:
    mapping_name: str
    role: str  # "source" | "target"
    system: str
    watermark_value: Optional[str] = None
    rows_by_key: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # Rows with an empty or duplicated matching key -- a dict keyed by
    # matching-key value can't represent these at all (empty keys collide,
    # duplicates would just collapse to "last one wins"), so they're kept
    # here as a plain list instead. Only ever rebuilt wholesale on a full
    # refresh; see src/sync_engine/compare.py's _fetch_rows_incremental for
    # why an incremental delta can't safely patch this list in place.
    unkeyed_rows: List[Dict[str, Any]] = field(default_factory=list)
    needed_fields_signature: str = ""
    last_full_refresh_at: Optional[str] = None


def fields_signature(needed_fields: Iterable[str]) -> str:
    """A stable string identifying exactly which fields a cache was built
    with -- if a mapping's declared fields change, the cache no longer
    reflects what compare_mapping() needs and must be rebuilt from scratch."""
    return ",".join(sorted(needed_fields))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cache_path(mapping_name: str, role: str) -> Path:
    filename = table_filename(f"{mapping_name}__{role}", suffix=".json")
    return state_path(f"sync_cache/{filename}", _DEFAULT_DIR)


def load_side_cache(mapping_name: str, role: str) -> Optional[MappingSideCache]:
    path = _cache_path(mapping_name, role)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return MappingSideCache(
        mapping_name=data.get("mapping_name", mapping_name),
        role=data.get("role", role),
        system=data.get("system", ""),
        watermark_value=data.get("watermark_value"),
        rows_by_key=data.get("rows_by_key") or {},
        unkeyed_rows=data.get("unkeyed_rows") or [],
        needed_fields_signature=data.get("needed_fields_signature", ""),
        last_full_refresh_at=data.get("last_full_refresh_at"),
    )


def save_side_cache(cache: MappingSideCache) -> None:
    path = _cache_path(cache.mapping_name, cache.role)
    payload = {
        "mapping_name": cache.mapping_name,
        "role": cache.role,
        "system": cache.system,
        "watermark_value": cache.watermark_value,
        "rows_by_key": cache.rows_by_key,
        "unkeyed_rows": cache.unkeyed_rows,
        "needed_fields_signature": cache.needed_fields_signature,
        "last_full_refresh_at": cache.last_full_refresh_at,
    }
    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)


def is_stale(
    cache: Optional[MappingSideCache],
    needed_fields_sig: str,
    *,
    max_age_hours: int = DEFAULT_MAX_AGE_HOURS,
) -> bool:
    """True when a full refresh is required instead of an incremental delta:
    no cache yet, the mapping's declared fields changed since the cache was
    built, or the last full refresh is old enough that a deletion on either
    side could otherwise go undetected indefinitely."""
    if cache is None:
        return True
    if cache.needed_fields_signature != needed_fields_sig:
        return True
    if cache.last_full_refresh_at is None:
        return True
    try:
        last = datetime.fromisoformat(cache.last_full_refresh_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    age_seconds = (datetime.now(timezone.utc) - last).total_seconds()
    return age_seconds > max_age_hours * 3600
