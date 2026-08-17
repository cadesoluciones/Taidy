# -*- coding: utf-8 -*-
"""
Read-only comparison engine for a saved sync mapping (webapp/sync_mappings.py).

Live-reads the current full state of both the source and target tables --
reusing each system's existing extraction client instead of a new one, and
called directly in-process rather than through webapp/tasks.py's subprocess
launcher, since this is read-only and fast enough (a few thousand rows) to
run synchronously from the API layer -- and classifies every record into
one of: create in target, create in source, update target (source is
newer), update source (target is newer), skipped (matching key missing or
duplicated), or unchanged.

This first pass has no notion of "changed since the last real sync" --
that requires a per-record checkpoint that only a real "Sincronizar" (a
later phase) can establish. Until a mapping has been synced at least once,
"update" here just means "the two sides' dates disagree right now", which
is the correct reading for a mapping that has never been reconciled.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


class SyncCompareError(RuntimeError):
    """Raised when a mapping can't be compared (bad config, missing secret, unreachable system, ...)."""


@dataclass
class RecordAction:
    key: str
    kind: str  # create_target | create_source | update_target | update_source | unchanged
    source_row: Optional[Dict[str, Any]] = None
    target_row: Optional[Dict[str, Any]] = None
    source_date: Optional[str] = None
    target_date: Optional[str] = None


@dataclass
class SkippedRecord:
    system: str  # "source" | "target"
    reason: str  # "empty_key" | "duplicate_key"
    key: str
    row: Dict[str, Any]


@dataclass
class ComparisonReport:
    mapping_name: str
    create_in_target: List[RecordAction] = field(default_factory=list)
    create_in_source: List[RecordAction] = field(default_factory=list)
    update_target: List[RecordAction] = field(default_factory=list)
    update_source: List[RecordAction] = field(default_factory=list)
    unchanged: List[RecordAction] = field(default_factory=list)
    skipped: List[SkippedRecord] = field(default_factory=list)


def _parse_date(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


# --------------------------------------------------------------------------------------
# Live readers -- one per system, each reusing that system's existing extraction client.
# --------------------------------------------------------------------------------------


def _fetch_bc_rows(table_name: str) -> List[Dict[str, Any]]:
    from src.bc_client.api import BusinessCentralClient
    from src.bc_client.auth import OAuthTokenProvider
    from src.bc_client.config import load_settings as load_bc_settings

    settings = load_bc_settings()
    table = next((t for t in settings.tables if t.name == table_name), None)
    if table is None:
        raise SyncCompareError(f"'{table_name}' no está declarada en tables.yaml.")

    secret = os.environ.get("BC_CLIENT_SECRET", "").strip()
    if not secret:
        raise SyncCompareError("Falta BC_CLIENT_SECRET en el entorno del servidor.")

    provider = OAuthTokenProvider(
        token_url=settings.token_url,
        client_id=settings.client_id,
        client_secret=secret,
        scope=settings.scope,
    )
    client = BusinessCentralClient(settings=settings, token_provider=provider)
    return client.get_table_rows(table.url, label=table_name)


def _fetch_hubspot_rows(table_name: str, needed_fields: Set[str]) -> List[Dict[str, Any]]:
    from src.hubspot_client.api import HubspotClient
    from src.hubspot_client.config import TableConfig as HubspotTableConfig
    from src.hubspot_client.config import load_settings as load_hubspot_settings

    settings = load_hubspot_settings()
    table = next((t for t in settings.tables if t.name == table_name), None)
    if table is None:
        raise SyncCompareError(f"'{table_name}' no está declarada en hubspot_tables.yaml.")

    # The mapping is the source of truth for which properties this comparison
    # needs -- not whatever hubspot_tables.yaml happens to already declare.
    fields = sorted(set(table.fields) | needed_fields)
    client = HubspotClient(settings=settings)
    return client.fetch_table(HubspotTableConfig(name=table.name, object_type=table.object_type, fields=fields))


def _fetch_factorial_rows(table_name: str) -> List[Dict[str, Any]]:
    from src.factorial_client.api import FactorialClient
    from src.factorial_client.config import load_settings as load_factorial_settings

    settings = load_factorial_settings()
    table = next((t for t in settings.tables if t.name == table_name), None)
    if table is None:
        raise SyncCompareError(f"'{table_name}' no está declarada en factorial_tables.yaml.")

    client = FactorialClient(settings=settings)
    today = date.today().isoformat()
    return client.fetch_table(table, start_on=today, end_on=today)


def fetch_rows(system: str, table_name: str, needed_fields: Set[str]) -> List[Dict[str, Any]]:
    if system == "business_central":
        return _fetch_bc_rows(table_name)
    if system == "hubspot":
        return _fetch_hubspot_rows(table_name, needed_fields)
    if system == "factorial":
        return _fetch_factorial_rows(table_name)
    raise SyncCompareError(f"Sistema desconocido: {system}")


# --------------------------------------------------------------------------------------
# Matching
# --------------------------------------------------------------------------------------


def _index_by_key(
    rows: List[Dict[str, Any]], key_field: str, *, system: str
) -> Tuple[Dict[str, Dict[str, Any]], List[SkippedRecord]]:
    index: Dict[str, Dict[str, Any]] = {}
    duplicate_keys: Set[str] = set()
    skipped: List[SkippedRecord] = []

    for row in rows:
        raw_key = row.get(key_field)
        key = str(raw_key).strip() if raw_key is not None else ""
        if not key:
            skipped.append(SkippedRecord(system=system, reason="empty_key", key="", row=row))
            continue
        if key in index:
            duplicate_keys.add(key)
        index[key] = row

    for dup_key in duplicate_keys:
        row = index.pop(dup_key, None)
        if row is not None:
            skipped.append(SkippedRecord(system=system, reason="duplicate_key", key=dup_key, row=row))

    return index, skipped


# --------------------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------------------


def compare_mapping(mapping_name: str) -> ComparisonReport:
    from dotenv import load_dotenv

    from webapp import sync_mappings

    # Unlike the CLI entry points (extract_bc, ...), the API server process
    # never loads .env itself -- this runs in-process from the API layer
    # (see api/routers/sync.py), so it has to load secrets the same way
    # those CLIs do, explicitly, right before reading them.
    load_dotenv()

    raw = next((m for m in sync_mappings.list_mappings_full() if m.get("name") == mapping_name), None)
    if raw is None:
        raise SyncCompareError(f"No existe el mapeo '{mapping_name}'.")

    source = raw["source"]
    target = raw["target"]
    matching_key = raw["matching_key"]
    date_field = raw["date_field"]
    fields = raw["fields"]

    needed_source_fields = {f["source"] for f in fields} | {matching_key["source"], date_field["source"]}
    needed_target_fields = {f["target"] for f in fields} | {matching_key["target"], date_field["target"]}

    source_rows = fetch_rows(source["system"], source["table"], needed_source_fields)
    target_rows = fetch_rows(target["system"], target["table"], needed_target_fields)

    source_index, source_skipped = _index_by_key(source_rows, matching_key["source"], system="source")
    target_index, target_skipped = _index_by_key(target_rows, matching_key["target"], system="target")

    report = ComparisonReport(mapping_name=mapping_name, skipped=source_skipped + target_skipped)

    for key, source_row in source_index.items():
        target_row = target_index.get(key)
        source_date = _parse_date(source_row.get(date_field["source"]))
        source_date_str = source_date.isoformat() if source_date else None

        if target_row is None:
            report.create_in_target.append(
                RecordAction(key=key, kind="create_target", source_row=source_row, source_date=source_date_str)
            )
            continue

        target_date = _parse_date(target_row.get(date_field["target"]))
        target_date_str = target_date.isoformat() if target_date else None
        action = RecordAction(
            key=key,
            kind="unchanged",
            source_row=source_row,
            target_row=target_row,
            source_date=source_date_str,
            target_date=target_date_str,
        )

        if source_date is None and target_date is None:
            report.unchanged.append(action)
        elif source_date is None:
            # Target is the only side with a track record -- it wins.
            action.kind = "update_source"
            report.update_source.append(action)
        elif target_date is None:
            action.kind = "update_target"
            report.update_target.append(action)
        elif source_date == target_date:
            report.unchanged.append(action)
        elif source_date > target_date:
            action.kind = "update_target"
            report.update_target.append(action)
        else:
            action.kind = "update_source"
            report.update_source.append(action)

    for key, target_row in target_index.items():
        if key in source_index:
            continue
        target_date = _parse_date(target_row.get(date_field["target"]))
        report.create_in_source.append(
            RecordAction(
                key=key,
                kind="create_source",
                target_row=target_row,
                target_date=target_date.isoformat() if target_date else None,
            )
        )

    return report
