# -*- coding: utf-8 -*-
"""
Write phase for a saved sync mapping (webapp/sync_mappings.py) -- applies
what src/sync_engine/compare.py's read-only comparison found, writing real
creates/updates to Business Central and HubSpot.

Business Central<->HubSpot only (see `_validate_mapping_shape`): identity
and anti-loop bookkeeping live entirely on the BC side, as three fields
added by a separate AL extension:
  - HubspotId (`hubspotId`): the linked HubSpot record's id.
  - BcLastSyncedAt / HubspotLastSyncedAt (`bcLastSyncedAt` /
    `hubspotLastSyncedAt`): informational timestamps, recorded after every
    successful write, for audit purposes.

Deciding "is this a real change, or just an echo of our own last write" is
NOT date-based -- BC's `SystemModifiedAt` is reassigned by the server the
moment it processes a write, so a checkpoint captured as part of that same
write can never exactly equal the value the write produces, and the gap
never closes on its own. Instead, before writing an update, the mapped
field VALUES already fetched by `compare_mapping()` are compared directly;
if they already match, there is nothing to write regardless of which side
the date-based classification picked as "newer" -- a successful sync always
leaves both sides holding identical content, so this closes the loop for
good rather than narrowing it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Set, Tuple

from .compare import RecordAction, compare_mapping

HUBSPOT_ID_FIELD = "hubspotId"
BC_CHECKPOINT_FIELD = "bcLastSyncedAt"
HUBSPOT_CHECKPOINT_FIELD = "hubspotLastSyncedAt"
# The OData property name for this entity's key on the custom API page,
# confirmed live against SANDBOX_CADE -- it's "id", not "systemId" (that's
# the AL/internal name for the same field; the API page exposes it as "id").
BC_KEY_FIELD = "id"

DEFAULT_THRESHOLD = 50

Direction = Literal["to_target", "to_source", "both"]


class SyncApplyError(RuntimeError):
    """Raised when a mapping can't be applied (bad config, unsupported
    systems, missing AL fields, ...)."""


class NeedsConfirmationError(SyncApplyError):
    """Raised before any write happens when the number of pending
    create+update actions exceeds the quantity circuit-breaker threshold
    and the caller hasn't explicitly confirmed."""

    def __init__(self, pending_count: int):
        self.pending_count = pending_count
        super().__init__(f"{pending_count} acciones pendientes superan el umbral de confirmación.")


@dataclass
class RecordResult:
    key: str
    kind: str
    outcome: str  # created | updated | skipped | failed
    detail: str = ""


@dataclass
class ApplyReport:
    mapping_name: str
    direction: str
    results: List[RecordResult] = field(default_factory=list)

    @property
    def created(self) -> int:
        return sum(1 for r in self.results if r.outcome == "created")

    @property
    def updated(self) -> int:
        return sum(1 for r in self.results if r.outcome == "updated")

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.outcome == "skipped")

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.outcome == "failed")


# --------------------------------------------------------------------------------------
# Mapping shape / precondition checks
# --------------------------------------------------------------------------------------


def _bc_side(mapping: dict) -> str:
    return "source" if mapping["source"]["system"] == "business_central" else "target"


def _validate_mapping_shape(mapping: dict) -> str:
    """Returns which side ("source"/"target") is Business Central, or raises
    if this mapping isn't a BC<->HubSpot pair (e.g. it involves Factorial,
    which this write phase doesn't support)."""
    systems = {mapping["source"]["system"], mapping["target"]["system"]}
    if systems != {"business_central", "hubspot"}:
        raise SyncApplyError(
            "Sincronizar solo admite mapeos entre Business Central y HubSpot "
            f"(este mapeo usa: {', '.join(sorted(systems))})."
        )
    return _bc_side(mapping)


def _ensure_bc_fields_exist(mapping: dict, bc_side: str) -> None:
    """Fails fast with a clear message if the BC table behind this mapping
    is missing the three fields the AL extension is supposed to add --
    instead of letting every write in the batch surface a cryptic OData
    'invalid property' error."""
    from src.bc_client.api import BusinessCentralClient
    from src.bc_client.auth import OAuthTokenProvider
    from src.bc_client.config import load_settings as load_bc_settings

    table, secret = _resolve_bc_table(mapping, bc_side)
    settings = load_bc_settings()
    provider = OAuthTokenProvider(
        token_url=settings.token_url, client_id=settings.client_id, client_secret=secret, scope=settings.scope
    )
    client = BusinessCentralClient(settings=settings, token_provider=provider)

    separator = "&" if "?" in table.url else "?"
    sample = client.get_table_rows(f"{table.url}{separator}$top=1", label=f"{table.name} (comprobación de campos)")
    if not sample:
        return  # Empty table -- can't verify ahead of time; a real write will surface any issue.

    missing = [f for f in (HUBSPOT_ID_FIELD, BC_CHECKPOINT_FIELD, HUBSPOT_CHECKPOINT_FIELD) if f not in sample[0]]
    if missing:
        raise SyncApplyError(
            "La tabla de Business Central de este mapeo no tiene los campos necesarios para "
            f"sincronizar ({', '.join(missing)}). Hace falta añadirlos primero mediante la "
            "extensión AL correspondiente."
        )


def _resolve_bc_table(mapping: dict, bc_side: str):
    from src.bc_client.config import load_settings as load_bc_settings

    bc_table_name = mapping[bc_side]["table"]
    settings = load_bc_settings()
    table = next((t for t in settings.tables if t.name == bc_table_name), None)
    if table is None:
        raise SyncApplyError(f"'{bc_table_name}' no está declarada en tables.yaml.")

    secret = os.environ.get("BC_CLIENT_SECRET", "").strip()
    if not secret:
        raise SyncApplyError("Falta BC_CLIENT_SECRET en el entorno del servidor.")

    return table, secret


# --------------------------------------------------------------------------------------
# No-op filter -- the actual anti-loop mechanism (see module docstring)
# --------------------------------------------------------------------------------------


def _normalize_value(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _values_already_match(action: RecordAction, mapping: dict) -> bool:
    """True if every mapped field already has the same value on both sides
    for this record -- nothing to actually write, regardless of which side
    the date-based comparison picked as "newer"."""
    for pair in mapping["fields"]:
        source_value = _normalize_value((action.source_row or {}).get(pair["source"]))
        target_value = _normalize_value((action.target_row or {}).get(pair["target"]))
        if source_value != target_value:
            return False
    return True


def _filter_no_op_updates(actions: List[RecordAction], mapping: dict) -> Tuple[List[RecordAction], List[RecordResult]]:
    kept: List[RecordAction] = []
    no_op: List[RecordResult] = []
    for action in actions:
        if _values_already_match(action, mapping):
            no_op.append(
                RecordResult(
                    key=action.key,
                    kind=action.kind,
                    outcome="skipped",
                    detail="Ya sincronizado -- sin cambios reales en los campos mapeados.",
                )
            )
        else:
            kept.append(action)
    return kept, no_op


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------------------


def apply_mapping(
    mapping_name: str,
    *,
    direction: Direction,
    confirmed: bool,
    threshold: int = DEFAULT_THRESHOLD,
    only_keys: Optional[Set[str]] = None,
) -> ApplyReport:
    """
    Args:
        only_keys: if given, restricts every group to just these matching-key
            values -- lets a caller (the "Comparar" UI's row checkboxes) apply
            only a hand-picked subset instead of every pending action.
            `None` means "no restriction", i.e. every pending action.
    """
    from dotenv import load_dotenv

    from webapp import sync_mappings

    # Same reasoning as compare_mapping(): this runs in-process from a
    # subprocess CLI, which doesn't auto-load .env either.
    load_dotenv()

    mapping = next((m for m in sync_mappings.list_mappings_full() if m.get("name") == mapping_name), None)
    if mapping is None:
        raise SyncApplyError(f"No existe el mapeo '{mapping_name}'.")

    bc_side = _validate_mapping_shape(mapping)
    _ensure_bc_fields_exist(mapping, bc_side)

    # Always recomputed now -- never trust a stale "Comparar" report from
    # the client. force_full=True also bypasses compare_mapping's own
    # incremental fetch cache (src/sync_engine/cache.py): that cache can't
    # see a recent deletion on either side, which is an acceptable staleness
    # window for the read-only "Comparar" preview but not for a real write.
    report = compare_mapping(mapping_name, force_full=True)

    results: List[RecordResult] = []
    groups: List[Tuple[str, List[RecordAction]]] = []

    if direction in ("to_target", "both"):
        groups.append(("create_target", report.create_in_target))
    if direction in ("to_source", "both"):
        groups.append(("create_source", report.create_in_source))
    if direction in ("to_target", "both"):
        kept, no_op = _filter_no_op_updates(report.update_target, mapping)
        results.extend(no_op)
        groups.append(("update_target", kept))
    if direction in ("to_source", "both"):
        kept, no_op = _filter_no_op_updates(report.update_source, mapping)
        results.extend(no_op)
        groups.append(("update_source", kept))

    if only_keys is not None:
        groups = [(kind, [a for a in actions if a.key in only_keys]) for kind, actions in groups]

    pending = sum(len(actions) for _, actions in groups)
    if pending > threshold and not confirmed:
        raise NeedsConfirmationError(pending_count=pending)

    for kind, actions in groups:
        if actions:
            results.extend(_apply_group(kind, actions, mapping, bc_side))

    return ApplyReport(mapping_name=mapping_name, direction=direction, results=results)


def count_pending_actions(report, direction: Direction, mapping: dict) -> int:
    """Same counting logic `apply_mapping` uses for the circuit breaker,
    exposed standalone so a caller (e.g. an API endpoint) can report the
    pending count without performing any write."""
    total = 0
    if direction in ("to_target", "both"):
        total += len(report.create_in_target)
        total += len(_filter_no_op_updates(report.update_target, mapping)[0])
    if direction in ("to_source", "both"):
        total += len(report.create_in_source)
        total += len(_filter_no_op_updates(report.update_source, mapping)[0])
    return total


# --------------------------------------------------------------------------------------
# Applying one group of actions (all same `kind`)
# --------------------------------------------------------------------------------------


def _apply_group(kind: str, actions: List[RecordAction], mapping: dict, bc_side: str) -> List[RecordResult]:
    target_is_bc = bc_side == "target"
    is_target_write = kind in ("create_target", "update_target")
    writes_to_bc = is_target_write == target_is_bc

    if writes_to_bc:
        return _apply_bc_group(kind, actions, mapping, bc_side)
    return _apply_hubspot_group(kind, actions, mapping, bc_side)


def _apply_bc_group(kind: str, actions: List[RecordAction], mapping: dict, bc_side: str) -> List[RecordResult]:
    """Writes actions whose destination is Business Central -- both a
    create (POST) and an update (PATCH, with a freshly re-read ETag) fold
    HubspotId/HubspotLastSyncedAt/BcLastSyncedAt into the same request,
    since BC is already the write target."""
    from src.bc_client.auth import OAuthTokenProvider
    from src.bc_client.config import load_settings as load_bc_settings
    from src.bc_client.write_api import BusinessCentralWriteClient, WriteOperation

    hubspot_is_source = kind in ("create_target", "update_target")
    field_pairs = [
        (
            pair["target"] if hubspot_is_source else pair["source"],
            pair["source"] if hubspot_is_source else pair["target"],
        )
        for pair in mapping["fields"]
    ]

    def hubspot_row_of(action: RecordAction) -> Dict[str, Any]:
        return (action.source_row if hubspot_is_source else action.target_row) or {}

    try:
        table, secret = _resolve_bc_table(mapping, bc_side)
    except SyncApplyError as exc:
        return [RecordResult(key=a.key, kind=kind, outcome="failed", detail=str(exc)) for a in actions]

    settings = load_bc_settings()
    provider = OAuthTokenProvider(
        token_url=settings.token_url, client_id=settings.client_id, client_secret=secret, scope=settings.scope
    )
    client = BusinessCentralWriteClient(token_provider=provider)

    is_update = kind in ("update_target", "update_source")
    matching_key_field = mapping["matching_key"][bc_side]

    fresh: Dict[str, Tuple[Dict[str, Any], str]] = {}
    if is_update:
        fresh = client.read_rows_with_etag(table.url, matching_key_field, [a.key for a in actions])

    results: List[RecordResult] = []
    operations: List[WriteOperation] = []
    action_by_content_id: Dict[int, RecordAction] = {}

    for content_id, action in enumerate(actions, start=1):
        hubspot_row = hubspot_row_of(action)
        body: Dict[str, Any] = {bc_field: hubspot_row.get(hubspot_field) for bc_field, hubspot_field in field_pairs}
        body[HUBSPOT_ID_FIELD] = hubspot_row.get("__hubspot_id")
        body[HUBSPOT_CHECKPOINT_FIELD] = _now_iso()
        body[BC_CHECKPOINT_FIELD] = _now_iso()

        if is_update:
            found = fresh.get(action.key)
            if found is None:
                results.append(
                    RecordResult(
                        key=action.key,
                        kind=kind,
                        outcome="failed",
                        detail="El registro ya no existe en Business Central (puede haberse borrado).",
                    )
                )
                continue
            row, etag = found
            operations.append(
                WriteOperation(content_id=content_id, method="PATCH", body=body, system_id=row.get(BC_KEY_FIELD), etag=etag)
            )
        else:
            operations.append(WriteOperation(content_id=content_id, method="POST", body=body))
        action_by_content_id[content_id] = action

    if operations:
        write_results = client.batch_write(table.url, operations)
        results.extend(
            _reconcile_bc_results(kind, operations, write_results, action_by_content_id, client, table.url, matching_key_field)
        )

    return results


def _reconcile_bc_results(
    kind: str,
    operations,
    write_results,
    action_by_content_id: Dict[int, RecordAction],
    client,
    table_url: str,
    matching_key_field: str,
) -> List[RecordResult]:
    """Maps `WriteResult`s back to `RecordResult`s, applying the confirmed
    412 policy: one retry with a freshly re-read ETag, then fail that one
    record and move on -- never abort the surrounding batch."""
    results: List[RecordResult] = []
    results_by_content_id = {r.content_id: r for r in write_results}
    retry_operations = []
    retry_action_by_content_id: Dict[int, RecordAction] = {}

    for op in operations:
        action = action_by_content_id[op.content_id]
        write_result = results_by_content_id.get(op.content_id)

        if write_result is None:
            results.append(RecordResult(key=action.key, kind=kind, outcome="failed", detail="Sin respuesta de Business Central para este registro."))
            continue

        if write_result.ok:
            outcome = "created" if op.method == "POST" else "updated"
            results.append(RecordResult(key=action.key, kind=kind, outcome=outcome))
            continue

        if write_result.status_code == 412 and op.method == "PATCH":
            from src.bc_client.write_api import WriteOperation

            fresh_row, fresh_etag = client.read_row_with_etag(table_url, matching_key_field, action.key)
            if fresh_row is not None and fresh_etag is not None:
                retry_operations.append(
                    WriteOperation(
                        content_id=op.content_id,
                        method="PATCH",
                        body=op.body,
                        system_id=fresh_row.get(BC_KEY_FIELD),
                        etag=fresh_etag,
                    )
                )
                retry_action_by_content_id[op.content_id] = action
                continue

        results.append(
            RecordResult(key=action.key, kind=kind, outcome="failed", detail=write_result.error_message or f"HTTP {write_result.status_code}")
        )

    if retry_operations:
        retry_results = client.batch_write(table_url, retry_operations)
        retry_by_content_id = {r.content_id: r for r in retry_results}
        for op in retry_operations:
            action = retry_action_by_content_id[op.content_id]
            write_result = retry_by_content_id.get(op.content_id)
            if write_result is not None and write_result.ok:
                results.append(RecordResult(key=action.key, kind=kind, outcome="updated"))
            else:
                detail = write_result.error_message if write_result is not None else "Sin respuesta de Business Central."
                results.append(
                    RecordResult(key=action.key, kind=kind, outcome="failed", detail=f"Conflicto persistente tras reintento: {detail}")
                )

    return results


def _apply_hubspot_group(kind: str, actions: List[RecordAction], mapping: dict, bc_side: str) -> List[RecordResult]:
    """Writes actions whose destination is HubSpot via batch upsert, then
    (only for records HubSpot confirmed successful) issues a separate
    follow-up BC batch to stamp HubspotId/BcLastSyncedAt/HubspotLastSyncedAt
    on the linked BC row. A HubSpot success followed by a checkpoint-stamp
    failure is still reported as created/updated (the real data write
    already succeeded) with the checkpoint issue surfaced via `detail`."""
    from src.hubspot_client.config import load_settings as load_hubspot_settings
    from src.hubspot_client.write_api import HubspotWriteClient, UpsertRecord

    target_write = kind in ("create_target", "update_target")
    hubspot_side = "target" if target_write else "source"
    hubspot_table_name = mapping[hubspot_side]["table"]
    id_property = mapping["matching_key"][hubspot_side]

    field_pairs = [
        (
            pair["target"] if target_write else pair["source"],
            pair["source"] if target_write else pair["target"],
        )
        for pair in mapping["fields"]
    ]

    def bc_row_of(action: RecordAction) -> Dict[str, Any]:
        return (action.source_row if target_write else action.target_row) or {}

    settings = load_hubspot_settings()
    table = next((t for t in settings.tables if t.name == hubspot_table_name), None)
    if table is None:
        detail = f"'{hubspot_table_name}' no está declarada en hubspot_tables.yaml."
        return [RecordResult(key=a.key, kind=kind, outcome="failed", detail=detail) for a in actions]

    client = HubspotWriteClient(settings=settings)
    records = []
    for action in actions:
        bc_row = bc_row_of(action)
        properties = {hubspot_field: bc_row.get(bc_field) for hubspot_field, bc_field in field_pairs}
        records.append(UpsertRecord(id_value=action.key, properties=properties))

    upsert_results = client.batch_upsert(table.object_type, id_property, records)
    upsert_by_key = {r.id_value: r for r in upsert_results}

    outcome_for = "created" if kind in ("create_target", "create_source") else "updated"
    results: List[RecordResult] = []
    successful: List[Tuple[RecordAction, Any]] = []

    for action in actions:
        upsert_result = upsert_by_key.get(action.key)
        if upsert_result is None or not upsert_result.ok:
            detail = upsert_result.error_message if upsert_result is not None else "Sin respuesta de HubSpot para este registro."
            results.append(RecordResult(key=action.key, kind=kind, outcome="failed", detail=detail))
            continue
        # The success RecordResult for this action is appended by
        # _stamp_bc_checkpoints below (every action in `successful` gets
        # exactly one there) -- not here, or it would be reported twice.
        successful.append((action, upsert_result))

    if successful:
        results.extend(_stamp_bc_checkpoints(kind, successful, mapping, bc_side, outcome_for))

    return results


def _stamp_bc_checkpoints(
    kind: str,
    successful: List[Tuple[RecordAction, Any]],
    mapping: dict,
    bc_side: str,
    outcome_for: str,
) -> List[RecordResult]:
    from src.bc_client.auth import OAuthTokenProvider
    from src.bc_client.config import load_settings as load_bc_settings
    from src.bc_client.write_api import BusinessCentralWriteClient, WriteOperation

    try:
        table, secret = _resolve_bc_table(mapping, bc_side)
    except SyncApplyError as exc:
        detail = f"Escrito en HubSpot, pero no se pudo anotar el checkpoint en BC: {exc}"
        return [RecordResult(key=a.key, kind=kind, outcome=outcome_for, detail=detail) for a, _ in successful]

    settings = load_bc_settings()
    provider = OAuthTokenProvider(
        token_url=settings.token_url, client_id=settings.client_id, client_secret=secret, scope=settings.scope
    )
    client = BusinessCentralWriteClient(token_provider=provider)

    matching_key_field = mapping["matching_key"][bc_side]
    fresh = client.read_rows_with_etag(table.url, matching_key_field, [a.key for a, _ in successful])

    results: List[RecordResult] = []
    operations: List[WriteOperation] = []
    action_by_content_id: Dict[int, RecordAction] = {}

    for content_id, (action, upsert_result) in enumerate(successful, start=1):
        found = fresh.get(action.key)
        if found is None:
            detail = "Escrito en HubSpot, pero ya no se encontró el registro en Business Central para anotar el checkpoint."
            results.append(RecordResult(key=action.key, kind=kind, outcome=outcome_for, detail=detail))
            continue
        row, etag = found
        body = {
            HUBSPOT_ID_FIELD: upsert_result.hubspot_id,
            HUBSPOT_CHECKPOINT_FIELD: _now_iso(),
            BC_CHECKPOINT_FIELD: _now_iso(),
        }
        operations.append(
            WriteOperation(content_id=content_id, method="PATCH", body=body, system_id=row.get(BC_KEY_FIELD), etag=etag)
        )
        action_by_content_id[content_id] = action

    if operations:
        write_results = client.batch_write(table.url, operations)
        write_by_content_id = {r.content_id: r for r in write_results}
        for content_id, action in action_by_content_id.items():
            write_result = write_by_content_id.get(content_id)
            if write_result is not None and write_result.ok:
                results.append(RecordResult(key=action.key, kind=kind, outcome=outcome_for))
            else:
                detail = write_result.error_message if write_result is not None else "Sin respuesta de Business Central."
                results.append(
                    RecordResult(
                        key=action.key,
                        kind=kind,
                        outcome=outcome_for,
                        detail=f"Escrito en HubSpot, pero falló anotar el checkpoint en BC: {detail}",
                    )
                )

    return results
