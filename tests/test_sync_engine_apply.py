# -*- coding: utf-8 -*-
"""
src/sync_engine/apply.py -- the write phase. Two layers are tested
separately:
  1. Orchestration (`apply_mapping` itself): ordering, the quantity
     circuit-breaker, and the no-op filter -- exercised with `_apply_group`
     and `_ensure_bc_fields_exist` stubbed out, since those belong to layer 2.
  2. Per-group write mechanics (`_apply_bc_group`/`_apply_hubspot_group`):
     exercised directly, with fake BC/HubSpot write clients injected at
     their source modules (matching how apply.py imports them lazily,
     inside the functions that use them).

Mapping orientation used throughout: source=hubspot, target=business_central
(bc_side="target" everywhere) -- so "create_target"/"update_target" always
write into BC, and "create_source"/"update_source" always write into
HubSpot. Field pairs are ("firstname" on HubSpot's side, "name" on BC's
side); row dicts use the field name that matches which system that row
actually came from.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.bc_client.config import Settings as BcSettings  # noqa: E402
from src.bc_client.config import TableConfig as BcTableConfig  # noqa: E402
from src.hubspot_client.config import Settings as HubspotSettings  # noqa: E402
from src.hubspot_client.config import TableConfig as HubspotTableConfig  # noqa: E402
from src.sync_engine import apply as apply_module  # noqa: E402
from src.sync_engine.compare import ComparisonReport, RecordAction  # noqa: E402


def _mapping(**overrides) -> dict:
    base = {
        "name": "hubspot_contacts_a_bc_contact",
        "source": {"system": "hubspot", "table": "hubspot_contacts"},
        "target": {"system": "business_central", "table": "bc_contact"},
        "matching_key": {"source": "email", "target": "email"},
        "date_field": {"source": "lastmodifieddate", "target": "systemModifiedAt"},
        "fields": [
            {"source": "email", "target": "email"},
            {"source": "firstname", "target": "name"},
        ],
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------------------
# Layer 1: orchestration
# --------------------------------------------------------------------------------------


@pytest.fixture
def no_precondition_check(monkeypatch):
    monkeypatch.setattr(apply_module, "_ensure_bc_fields_exist", lambda *a, **k: None)


@pytest.fixture
def fake_mappings(monkeypatch):
    from webapp import sync_mappings

    mapping = _mapping()
    monkeypatch.setattr(sync_mappings, "list_mappings_full", lambda: [mapping])
    return mapping


def test_apply_mapping_rejects_a_factorial_involving_mapping(no_precondition_check, monkeypatch):
    from webapp import sync_mappings

    mapping = _mapping(source={"system": "factorial", "table": "x"})
    monkeypatch.setattr(sync_mappings, "list_mappings_full", lambda: [mapping])

    with pytest.raises(apply_module.SyncApplyError, match="Business Central y HubSpot"):
        apply_module.apply_mapping(mapping["name"], direction="both", confirmed=False)


def _action(key: str, kind: str) -> RecordAction:
    return RecordAction(key=key, kind=kind, source_row={"email": key}, target_row={"email": key})


def test_apply_mapping_raises_needs_confirmation_before_any_write(no_precondition_check, fake_mappings, monkeypatch):
    report = ComparisonReport(
        mapping_name=fake_mappings["name"],
        create_in_target=[_action(f"c{i}@x.com", "create_target") for i in range(51)],
    )
    monkeypatch.setattr(apply_module, "compare_mapping", lambda name, **kwargs: report)

    called = []
    monkeypatch.setattr(apply_module, "_apply_group", lambda *a, **k: called.append(a) or [])

    with pytest.raises(apply_module.NeedsConfirmationError) as exc_info:
        apply_module.apply_mapping(fake_mappings["name"], direction="to_target", confirmed=False)

    assert exc_info.value.pending_count == 51
    assert called == []  # no write attempted


def test_apply_mapping_proceeds_when_confirmed_even_over_threshold(no_precondition_check, fake_mappings, monkeypatch):
    report = ComparisonReport(
        mapping_name=fake_mappings["name"],
        create_in_target=[_action(f"c{i}@x.com", "create_target") for i in range(51)],
    )
    monkeypatch.setattr(apply_module, "compare_mapping", lambda name, **kwargs: report)
    monkeypatch.setattr(apply_module, "_apply_group", lambda kind, actions, mapping, bc_side: [])

    result = apply_module.apply_mapping(fake_mappings["name"], direction="to_target", confirmed=True)
    assert result.mapping_name == fake_mappings["name"]


def test_apply_mapping_dispatches_groups_in_create_then_update_order(no_precondition_check, fake_mappings, monkeypatch):
    report = ComparisonReport(
        mapping_name=fake_mappings["name"],
        create_in_target=[_action("ct@x.com", "create_target")],
        create_in_source=[_action("cs@x.com", "create_source")],
        update_target=[_action("ut@x.com", "update_target")],
        update_source=[_action("us@x.com", "update_source")],
    )
    # Make every update look like a real change (values differ) so none are
    # filtered out as no-ops -- source's "firstname" vs target's "name".
    for a in report.update_target + report.update_source:
        a.source_row["firstname"] = "Changed"
    monkeypatch.setattr(apply_module, "compare_mapping", lambda name, **kwargs: report)

    dispatched = []
    monkeypatch.setattr(apply_module, "_apply_group", lambda kind, actions, mapping, bc_side: dispatched.append(kind) or [])

    apply_module.apply_mapping(fake_mappings["name"], direction="both", confirmed=True)

    assert dispatched == ["create_target", "create_source", "update_target", "update_source"]


def test_apply_mapping_only_keys_restricts_dispatch_and_the_threshold_count(no_precondition_check, fake_mappings, monkeypatch):
    report = ComparisonReport(
        mapping_name=fake_mappings["name"],
        create_in_target=[_action(f"c{i}@x.com", "create_target") for i in range(60)],
    )
    monkeypatch.setattr(apply_module, "compare_mapping", lambda name, **kwargs: report)

    dispatched = []
    monkeypatch.setattr(apply_module, "_apply_group", lambda kind, actions, mapping, bc_side: dispatched.append(list(actions)) or [])

    # 60 pending in total (over the 50 threshold), but only 2 are selected --
    # should neither need confirmation nor dispatch the other 58.
    result = apply_module.apply_mapping(
        fake_mappings["name"], direction="to_target", confirmed=False, only_keys={"c0@x.com", "c5@x.com"}
    )

    assert len(dispatched) == 1
    assert {a.key for a in dispatched[0]} == {"c0@x.com", "c5@x.com"}
    assert result.mapping_name == fake_mappings["name"]


def test_apply_mapping_filters_no_op_updates_before_dispatch_and_before_counting(no_precondition_check, fake_mappings, monkeypatch):
    # source (hubspot) and target (BC) already hold the same mapped value -- nothing to write.
    no_op_action = RecordAction(
        key="same@x.com",
        kind="update_target",
        source_row={"email": "same@x.com", "firstname": "Ana", "lastmodifieddate": "2026-03-01T00:00:00Z"},
        target_row={"email": "same@x.com", "name": "Ana", "systemModifiedAt": "2026-01-01T00:00:00Z"},
    )
    report = ComparisonReport(mapping_name=fake_mappings["name"], update_target=[no_op_action])
    monkeypatch.setattr(apply_module, "compare_mapping", lambda name, **kwargs: report)

    dispatched = []
    monkeypatch.setattr(apply_module, "_apply_group", lambda kind, actions, mapping, bc_side: dispatched.append((kind, actions)) or [])

    result = apply_module.apply_mapping(fake_mappings["name"], direction="to_target", confirmed=False)

    # Never dispatched (nothing to write, so _apply_group isn't even called)
    # and never counted toward the threshold.
    assert dispatched == []
    assert len(result.results) == 1
    assert result.results[0].outcome == "skipped"
    assert result.skipped == 1


def test_apply_mapping_always_forces_a_full_comparison(no_precondition_check, fake_mappings, monkeypatch):
    # apply_mapping must never write based on a possibly-stale incremental
    # cache (src/sync_engine/cache.py) -- a recent deletion on either side
    # has to be visible before any real write happens.
    report = ComparisonReport(mapping_name=fake_mappings["name"])
    calls = []

    def fake_compare_mapping(name, **kwargs):
        calls.append((name, kwargs))
        return report

    monkeypatch.setattr(apply_module, "compare_mapping", fake_compare_mapping)
    monkeypatch.setattr(apply_module, "_apply_group", lambda kind, actions, mapping, bc_side: [])

    apply_module.apply_mapping(fake_mappings["name"], direction="to_target", confirmed=False)

    assert calls == [(fake_mappings["name"], {"force_full": True})]


# --------------------------------------------------------------------------------------
# Layer 2: BC-destination writes ("create_target"/"update_target" -- bc_side="target")
# --------------------------------------------------------------------------------------


class _FakeBcWriteClient:
    etag_lookup = {}
    write_results_by_content_id = {}
    batches = []

    def __init__(self, *, token_provider):
        pass

    def read_rows_with_etag(self, table_url, key_field, key_values):
        return {k: v for k, v in type(self).etag_lookup.items() if k in key_values}

    def read_row_with_etag(self, table_url, key_field, key_value):
        return type(self).etag_lookup.get(key_value, (None, None))

    def batch_write(self, table_url, operations):
        type(self).batches.append((table_url, list(operations)))
        return [type(self).write_results_by_content_id[op.content_id] for op in operations]


class _FakeHubspotWriteClient:
    upsert_results_by_id_value = {}
    calls = []

    def __init__(self, *, settings):
        pass

    def batch_upsert(self, object_type, id_property, records):
        type(self).calls.append((object_type, id_property, list(records)))
        return [type(self).upsert_results_by_id_value[r.id_value] for r in records]


@pytest.fixture(autouse=True)
def _reset_fakes():
    _FakeBcWriteClient.etag_lookup = {}
    _FakeBcWriteClient.write_results_by_content_id = {}
    _FakeBcWriteClient.batches = []
    _FakeHubspotWriteClient.upsert_results_by_id_value = {}
    _FakeHubspotWriteClient.calls = []
    yield


@pytest.fixture
def bc_write_client(monkeypatch):
    monkeypatch.setattr("src.bc_client.write_api.BusinessCentralWriteClient", _FakeBcWriteClient)
    monkeypatch.setattr(
        "src.bc_client.config.load_settings",
        lambda: BcSettings(
            tenant_id="t",
            client_id="c",
            client_secret="s",
            scope="scope",
            token_url="https://login.microsoftonline.com/t/oauth2/v2.0/token",
            company_id=None,
            company_name="ACME",
            tables=[BcTableConfig(name="bc_contact", url="https://api.example/contacts")],
            page_size=1000,
            output_dir=Path("."),
        ),
    )
    monkeypatch.setenv("BC_CLIENT_SECRET", "fake-secret")
    return _FakeBcWriteClient


def _write_result(content_id, ok, status_code=200, error_message=None, body=None):
    from src.bc_client.write_api import WriteResult

    return WriteResult(content_id=content_id, ok=ok, status_code=status_code, body=body, error_message=error_message)


def test_apply_bc_group_create_includes_hubspot_id_and_checkpoint_fields(bc_write_client):
    mapping = _mapping()
    action = RecordAction(
        key="a@x.com",
        kind="create_target",
        source_row={"email": "a@x.com", "firstname": "Ana", "__hubspot_id": "hs-1"},
    )
    _FakeBcWriteClient.write_results_by_content_id = {1: _write_result(1, ok=True, status_code=201, body={"id": "new-guid"})}

    results = apply_module._apply_bc_group("create_target", [action], mapping, bc_side="target")

    assert len(results) == 1
    assert results[0].outcome == "created"
    table_url, operations = _FakeBcWriteClient.batches[0]
    op = operations[0]
    assert op.method == "POST"
    assert op.body["email"] == "a@x.com"
    assert op.body["name"] == "Ana"
    assert op.body[apply_module.HUBSPOT_ID_FIELD] == "hs-1"
    assert apply_module.BC_CHECKPOINT_FIELD in op.body
    assert apply_module.HUBSPOT_CHECKPOINT_FIELD in op.body


def test_apply_bc_group_update_uses_fresh_etag(bc_write_client):
    mapping = _mapping()
    action = RecordAction(
        key="a@x.com",
        kind="update_target",
        source_row={"email": "a@x.com", "firstname": "Ana", "__hubspot_id": "hs-1"},
        target_row={"email": "a@x.com", "name": "Ana Vieja", "id": "sys-1"},
    )
    _FakeBcWriteClient.etag_lookup = {"a@x.com": ({"id": "sys-1"}, 'W/"fresh"')}
    _FakeBcWriteClient.write_results_by_content_id = {1: _write_result(1, ok=True)}

    results = apply_module._apply_bc_group("update_target", [action], mapping, bc_side="target")

    assert results[0].outcome == "updated"
    _, operations = _FakeBcWriteClient.batches[0]
    assert operations[0].method == "PATCH"
    assert operations[0].etag == 'W/"fresh"'
    assert operations[0].system_id == "sys-1"


def test_apply_bc_group_retries_once_on_412_then_fails(bc_write_client):
    mapping = _mapping()
    action = RecordAction(
        key="a@x.com",
        kind="update_target",
        source_row={"email": "a@x.com", "firstname": "Ana", "__hubspot_id": "hs-1"},
        target_row={"email": "a@x.com", "name": "Ana Vieja", "id": "sys-1"},
    )
    _FakeBcWriteClient.etag_lookup = {"a@x.com": ({"id": "sys-1"}, 'W/"v1"')}
    # Both the initial batch_write call and the retry call reuse content_id=1
    # (see _reconcile_bc_results) and both 412 here.
    calls = {"n": 0}
    original_batch_write = _FakeBcWriteClient.batch_write

    def batch_write(self, table_url, operations):
        calls["n"] += 1
        return [_write_result(1, ok=False, status_code=412, error_message="conflict")]

    _FakeBcWriteClient.batch_write = batch_write
    try:
        results = apply_module._apply_bc_group("update_target", [action], mapping, bc_side="target")
    finally:
        _FakeBcWriteClient.batch_write = original_batch_write

    assert calls["n"] == 2  # one retry, then give up
    assert results[0].outcome == "failed"
    assert "reintento" in results[0].detail.lower()


def test_apply_bc_group_one_failure_does_not_affect_other_records(bc_write_client):
    mapping = _mapping()
    actions = [
        RecordAction(key="good@x.com", kind="create_target", source_row={"email": "good@x.com", "firstname": "G"}),
        RecordAction(key="bad@x.com", kind="create_target", source_row={"email": "bad@x.com", "firstname": "B"}),
    ]
    _FakeBcWriteClient.write_results_by_content_id = {
        1: _write_result(1, ok=True, status_code=201),
        2: _write_result(2, ok=False, status_code=400, error_message="invalid"),
    }

    results = {r.key: r for r in apply_module._apply_bc_group("create_target", actions, mapping, bc_side="target")}

    assert results["good@x.com"].outcome == "created"
    assert results["bad@x.com"].outcome == "failed"


# --------------------------------------------------------------------------------------
# Layer 2: HubSpot-destination writes ("create_source"/"update_source" -- bc_side="target")
# --------------------------------------------------------------------------------------


def _upsert_result(id_value, ok, hubspot_id=None, error_message=None):
    from src.hubspot_client.write_api import UpsertResult

    return UpsertResult(id_value=id_value, ok=ok, hubspot_id=hubspot_id, error_message=error_message)


@pytest.fixture
def hubspot_write_client(monkeypatch, bc_write_client):
    monkeypatch.setattr("src.hubspot_client.write_api.HubspotWriteClient", _FakeHubspotWriteClient)
    monkeypatch.setattr(
        "src.hubspot_client.config.load_settings",
        lambda: HubspotSettings(
            api_key="fake-key",
            tables=[HubspotTableConfig(name="hubspot_contacts", object_type="contacts", fields=["email", "firstname"])],
        ),
    )
    return _FakeHubspotWriteClient


def test_apply_hubspot_group_stamps_bc_checkpoint_only_for_confirmed_successes(hubspot_write_client):
    mapping = _mapping()
    actions = [
        RecordAction(
            key="ok@x.com",
            kind="create_source",
            target_row={"email": "ok@x.com", "name": "OK", "id": "sys-ok"},
        ),
        RecordAction(
            key="fail@x.com",
            kind="create_source",
            target_row={"email": "fail@x.com", "name": "Fail", "id": "sys-fail"},
        ),
    ]
    _FakeHubspotWriteClient.upsert_results_by_id_value = {
        "ok@x.com": _upsert_result("ok@x.com", ok=True, hubspot_id="hs-new-1"),
        "fail@x.com": _upsert_result("fail@x.com", ok=False, error_message="bad email"),
    }
    _FakeBcWriteClient.etag_lookup = {"ok@x.com": ({"id": "sys-ok"}, 'W/"v1"')}
    _FakeBcWriteClient.write_results_by_content_id = {1: _write_result(1, ok=True)}

    results = {r.key: r for r in apply_module._apply_hubspot_group("create_source", actions, mapping, bc_side="target")}

    assert results["ok@x.com"].outcome == "created"
    assert results["fail@x.com"].outcome == "failed"

    # Only the successful HubSpot write triggered a BC checkpoint PATCH.
    _, operations = _FakeBcWriteClient.batches[0]
    assert len(operations) == 1
    assert operations[0].body[apply_module.HUBSPOT_ID_FIELD] == "hs-new-1"


def test_apply_hubspot_group_reports_success_even_if_checkpoint_stamp_fails(hubspot_write_client):
    mapping = _mapping()
    action = RecordAction(key="ok@x.com", kind="create_source", target_row={"email": "ok@x.com", "name": "OK", "id": "sys-ok"})
    _FakeHubspotWriteClient.upsert_results_by_id_value = {"ok@x.com": _upsert_result("ok@x.com", ok=True, hubspot_id="hs-1")}
    _FakeBcWriteClient.etag_lookup = {"ok@x.com": ({"id": "sys-ok"}, 'W/"v1"')}
    _FakeBcWriteClient.write_results_by_content_id = {1: _write_result(1, ok=False, status_code=500, error_message="boom")}

    results = apply_module._apply_hubspot_group("create_source", [action], mapping, bc_side="target")

    assert len(results) == 1
    # The real HubSpot write succeeded -- must not be reported as failed.
    assert results[0].outcome == "created"
    assert "checkpoint" in results[0].detail.lower() or "boom" in results[0].detail.lower()
