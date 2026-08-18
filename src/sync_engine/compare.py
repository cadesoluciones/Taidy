# -*- coding: utf-8 -*-
"""
Read-only comparison engine for a saved sync mapping (webapp/sync_mappings.py).

Live-reads the current state of both the source and target tables -- reusing
each system's existing extraction client instead of a new one, and called
directly in-process rather than through webapp/tasks.py's subprocess
launcher, since this is read-only and fast enough to run synchronously from
the API layer -- and classifies every record into one of: create in target,
create in source, update target (source is newer), update source (target is
newer), skipped (matching key missing or duplicated), or unchanged.

For business_central/hubspot, "live-reads the current state" no longer means
"re-fetches every row every time": src/sync_engine/cache.py persists the
last known full row set per (mapping, source/target side), and each call
here only fetches what changed since that cache's watermark, merging the
delta on top of it (see `_fetch_rows_incremental`). The diff/classification
logic below is completely unaware of this -- it always receives the same
logically-complete row set it always did, just assembled from cache+delta
instead of a full fetch. Factorial-involving mappings are unaffected --
they keep going through the plain `fetch_rows` path with no caching, since
they're never a valid target for the real write phase anyway (see
src/sync_engine/apply.py's BC<->HubSpot-only restriction).

Neither BC nor HubSpot exposes deletions as an incremental "change", so a
mapping's cache is also forced to fully refresh periodically regardless of
its watermark (see cache.is_stale's max_age_hours) -- this bounds how stale
"record no longer exists on this side" detection can get, rather than
letting it go undetected forever. `compare_mapping(..., force_full=True)`
(used by the real "Sincronizar" write phase) skips the cache outright: a
write should never be decided from a comparison that might be missing a
recent deletion.

This first pass still has no notion of "changed since the last real
*sync*" for conflict-resolution purposes -- that's a separate concern from
the fetch-caching above, solved by comparing actual field values before
writing (see src/sync_engine/apply.py), not by anything here. Until a
mapping has been synced at least once, "update" here just means "the two
sides' dates disagree right now", which is the correct reading for a
mapping that has never been reconciled.
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

from src.sync_engine import cache as sync_cache  # noqa: E402


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


def _bc_client_and_table(table_name: str):
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
    return client, table


def _fetch_bc_rows(table_name: str) -> List[Dict[str, Any]]:
    client, table = _bc_client_and_table(table_name)
    return client.get_table_rows(table.url, label=table_name)


def _fetch_bc_rows_since(table_name: str, date_field: str, since: str) -> List[Dict[str, Any]]:
    """Same OData `$filter=<field> gt <value>` incremental pattern already
    proven for BC's own extraction pipeline (src/ingest/jobs.py), but using
    the mapping's own date_field name (a custom API page's OData property,
    e.g. `systemModifiedAt`) instead of that module's hardcoded `SystemModifiedAt`."""
    from src.utils.url import merge_query_params

    client, table = _bc_client_and_table(table_name)
    url = merge_query_params(table.url, {"$filter": f"{date_field} gt {since}", "$orderby": f"{date_field} asc"})
    return client.get_table_rows(url, label=f"{table_name} (incremental)")


def _hubspot_client_and_table(table_name: str, needed_fields: Set[str]):
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
    return client, HubspotTableConfig(name=table.name, object_type=table.object_type, fields=fields)


def _fetch_hubspot_rows(table_name: str, needed_fields: Set[str]) -> List[Dict[str, Any]]:
    client, table_config = _hubspot_client_and_table(table_name, needed_fields)
    # fetch_table_with_ids (not fetch_table) so every row carries HubSpot's
    # own record id under "__hubspot_id" -- the write phase (src/sync_engine/
    # apply.py) needs it to update an existing record or to link a newly
    # created one back into Business Central's HubspotId field.
    return client.fetch_table_with_ids(table_config)


def _fetch_hubspot_rows_since(
    table_name: str, needed_fields: Set[str], date_field: str, since: str
) -> List[Dict[str, Any]]:
    client, table_config = _hubspot_client_and_table(table_name, needed_fields)
    since_dt = _parse_date(since)
    if since_dt is None:
        raise SyncCompareError(f"No se pudo interpretar la fecha de checkpoint '{since}' para el fetch incremental.")
    return client.search_table_with_ids(
        table_config, date_field=date_field, modified_since_epoch_ms=int(since_dt.timestamp() * 1000)
    )


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


def _fetch_since(system: str, table_name: str, needed_fields: Set[str], date_field: str, since: str) -> List[Dict[str, Any]]:
    if system == "business_central":
        return _fetch_bc_rows_since(table_name, date_field, since)
    if system == "hubspot":
        return _fetch_hubspot_rows_since(table_name, needed_fields, date_field, since)
    raise SyncCompareError(f"Sistema sin fetch incremental: {system}")


# --------------------------------------------------------------------------------------
# Incremental fetch -- merges a delta (or a full fetch, when the cache is
# stale/absent/force_full) into the persisted per-(mapping, side) cache, and
# always returns the full logically-complete row set so the diff logic below
# never has to know the difference. See cache.py and the module docstring.
# --------------------------------------------------------------------------------------


def _apply_row_filter(rows: List[Dict[str, Any]], row_filter: Optional[Dict[str, str]]) -> List[Dict[str, Any]]:
    """Restricts a fetched row set to `row_filter["field"] == row_filter["equals"]`
    (string comparison), or returns it unchanged if there's no filter. This is
    how a mapping opts into only a subset of a shared table -- e.g. Business
    Central's bc_contact holds both Person and Company records, and only one
    of them belongs in a given HubSpot object. Applied in-memory, right after
    fetching and before anything else (caching, key indexing) sees the rows,
    so a mapping's cache only ever reflects what it actually cares about, and
    the same logic works identically for every system without a per-system
    query-filter implementation."""
    if not row_filter:
        return rows
    field = row_filter["field"]
    expected = row_filter["equals"]
    return [row for row in rows if str(row.get(field, "")) == expected]


def _row_key(row: Dict[str, Any], key_field: str) -> str:
    raw_key = row.get(key_field)
    return str(raw_key).strip() if raw_key is not None else ""


def _partition_rows_by_key(
    rows: List[Dict[str, Any]], key_field: str
) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
    """Splits rows into (uniquely-keyed rows, everything else), mirroring
    exactly what `_index_by_key` below flags as skipped during
    classification: an empty key, or a key shared by more than one row (in
    which case every row sharing it lands in the second list, not just the
    extras). A dict keyed by matching-key value can't represent either case
    -- empty keys would collide with each other and duplicates would
    silently collapse to "last one wins" -- so the incremental cache
    (src/sync_engine/cache.py) keeps them in a separate plain list instead,
    to avoid quietly turning a skipped record into a "valid" one."""
    by_key: Dict[str, List[Dict[str, Any]]] = {}
    unkeyed: List[Dict[str, Any]] = []
    for row in rows:
        key = _row_key(row, key_field)
        if not key:
            unkeyed.append(row)
            continue
        by_key.setdefault(key, []).append(row)

    unique: Dict[str, Dict[str, Any]] = {}
    for key, group in by_key.items():
        if len(group) == 1:
            unique[key] = group[0]
        else:
            unkeyed.extend(group)
    return unique, unkeyed


def _max_field_value(rows: List[Dict[str, Any]], field_name: str) -> Optional[str]:
    values = [str(r[field_name]) for r in rows if r.get(field_name)]
    return max(values) if values else None


def _fetch_rows_incremental(
    system: str,
    table_name: str,
    needed_fields: Set[str],
    *,
    mapping_name: str,
    role: str,
    date_field: str,
    key_field: str,
    force_full: bool,
    row_filter: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """
    Returns the logically-complete row set (cache + delta), but keeps two
    representations distinct:
      - `result_rows` (returned): the *raw* rows just fetched, concatenated
        with whatever cached rows weren't part of this fetch. This is what
        feeds compare_mapping's _index_by_key -- it must see the same raw,
        possibly-duplicate/empty-key rows a full fetch always would, or
        empty-key/duplicate-key skip detection would silently break.
      - `cache_rows_by_key` / `cache_unkeyed_rows` (persisted): a clean
        key->row dict for uniquely-keyed rows, plus a separate list for
        everything else (empty key, or a key shared by more than one row).
        The unkeyed list is only ever rebuilt wholesale on a full refresh --
        an incremental delta can't safely resolve "is this duplicate group
        still duplicated?" without re-fetching everything, so a key already
        known to be unkeyed stays that way (even if this delta happens to
        show it alone) until the next full refresh confirms otherwise.

    `row_filter`, when given, is applied to every freshly-fetched row right
    away (see `_apply_row_filter`) -- so the persisted cache only ever holds
    rows this mapping actually cares about, and everything below (watermark,
    key partitioning) operates on that already-filtered set as if it were
    the whole table.
    """
    filter_sig = f"|filter:{row_filter['field']}={row_filter['equals']}" if row_filter else ""
    fields_sig = sync_cache.fields_signature(needed_fields | {key_field, date_field}) + filter_sig
    cache = sync_cache.load_side_cache(mapping_name, role)
    do_full = force_full or sync_cache.is_stale(cache, fields_sig)

    if do_full:
        fetched = fetch_rows(system, table_name, needed_fields)
        new_rows = _apply_row_filter(fetched, row_filter)
        result_rows = list(new_rows)
        cache_rows_by_key, cache_unkeyed_rows = _partition_rows_by_key(new_rows, key_field)
        last_full_refresh_at = sync_cache.now_iso()
    else:
        since = cache.watermark_value if cache else None
        fetched = _fetch_since(system, table_name, needed_fields, date_field, since) if since else fetch_rows(
            system, table_name, needed_fields
        )
        # touched_keys is computed from the *unfiltered* fetch, not new_rows
        # below -- a row that changed and no longer passes the filter (e.g.
        # its `type` flipped from Person to Company) must still evict its
        # stale, now-wrong cached entry, even though it won't be re-added.
        new_rows = _apply_row_filter(fetched, row_filter)
        new_unique, new_unkeyed = _partition_rows_by_key(new_rows, key_field)

        previously_unkeyed_keys = {
            _row_key(row, key_field) for row in (cache.unkeyed_rows if cache else []) if _row_key(row, key_field)
        }
        for key in list(new_unique):
            if key in previously_unkeyed_keys:
                new_unkeyed.append(new_unique.pop(key))

        # Every key this delta touched (whether it resolved to unique, to
        # unkeyed, or was filtered out entirely) supersedes whatever the
        # cache remembered for it, so it's never carried forward AND
        # counted again below.
        touched_keys = {_row_key(row, key_field) for row in fetched if _row_key(row, key_field)}

        stale_cached_rows = [
            row for key, row in (cache.rows_by_key.items() if cache else []) if key not in touched_keys
        ]
        stale_unkeyed_rows = [
            row for row in (cache.unkeyed_rows if cache else []) if _row_key(row, key_field) not in touched_keys
        ]
        # Empty-key rows have no identity to dedupe by, so old and freshly-
        # seen ones both stay -- possible double-counting of the same
        # underlying record is bounded by the periodic full refresh, same as
        # the deletion-detection tradeoff documented in cache.py.

        result_rows = stale_cached_rows + stale_unkeyed_rows + list(new_rows)

        cache_rows_by_key = dict(cache.rows_by_key) if cache else {}
        for key in touched_keys:
            cache_rows_by_key.pop(key, None)
        cache_rows_by_key.update(new_unique)

        cache_unkeyed_rows = stale_unkeyed_rows + new_unkeyed
        last_full_refresh_at = cache.last_full_refresh_at if cache else sync_cache.now_iso()

    # The watermark tracks how far we've read the underlying stream, not the
    # filtered view -- computed from `fetched` (pre-filter) so a row that
    # changed but no longer passes the filter still advances it, instead of
    # that change being re-fetched forever.
    new_watermark = _max_field_value(fetched, date_field) or (cache.watermark_value if cache else None)

    sync_cache.save_side_cache(
        sync_cache.MappingSideCache(
            mapping_name=mapping_name,
            role=role,
            system=system,
            watermark_value=new_watermark,
            rows_by_key=cache_rows_by_key,
            unkeyed_rows=cache_unkeyed_rows,
            needed_fields_signature=fields_sig,
            last_full_refresh_at=last_full_refresh_at,
        )
    )

    return result_rows


def _fetch_rows_for_side(
    system: str,
    table_name: str,
    needed_fields: Set[str],
    *,
    mapping_name: str,
    role: str,
    date_field: str,
    key_field: str,
    force_full: bool,
    row_filter: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """BC/HubSpot go through the incremental cache; Factorial (never a valid
    target for the real write phase, see apply.py) keeps the old plain
    full-fetch-every-time behavior, untouched (but still respects a
    row_filter, for consistency, should a Factorial mapping ever need one)."""
    if system in ("business_central", "hubspot"):
        return _fetch_rows_incremental(
            system,
            table_name,
            needed_fields,
            mapping_name=mapping_name,
            role=role,
            date_field=date_field,
            key_field=key_field,
            force_full=force_full,
            row_filter=row_filter,
        )
    return _apply_row_filter(fetch_rows(system, table_name, needed_fields), row_filter)


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


def compare_mapping(mapping_name: str, *, force_full: bool = False) -> ComparisonReport:
    """
    Args:
        force_full: bypass both sides' caches and do a full fetch regardless
            of watermark freshness. The real write phase (src/sync_engine/
            apply.py) always passes True -- a write should never be decided
            from a comparison that might be missing a recent deletion.
    """
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
    source_filter = raw.get("source_filter")
    target_filter = raw.get("target_filter")

    needed_source_fields = {f["source"] for f in fields} | {matching_key["source"], date_field["source"]}
    needed_target_fields = {f["target"] for f in fields} | {matching_key["target"], date_field["target"]}
    # HubSpot only returns properties explicitly requested (unlike BC, which
    # always returns every exposed field) -- the filtered-on field has to be
    # requested too, or it would come back missing and _apply_row_filter
    # would treat every row as failing the filter.
    if source_filter:
        needed_source_fields.add(source_filter["field"])
    if target_filter:
        needed_target_fields.add(target_filter["field"])

    source_rows = _fetch_rows_for_side(
        source["system"],
        source["table"],
        needed_source_fields,
        mapping_name=mapping_name,
        role="source",
        date_field=date_field["source"],
        key_field=matching_key["source"],
        force_full=force_full,
        row_filter=source_filter,
    )
    target_rows = _fetch_rows_for_side(
        target["system"],
        target["table"],
        needed_target_fields,
        mapping_name=mapping_name,
        role="target",
        date_field=date_field["target"],
        key_field=matching_key["target"],
        row_filter=target_filter,
        force_full=force_full,
    )

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
