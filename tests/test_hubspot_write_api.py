# -*- coding: utf-8 -*-
"""
src/hubspot_client/write_api.py -- HubSpot's batch upsert isn't true
partial-failure like BC's $batch (a single bad input can fail the whole
call), so the "shrink and retry" logic is the main thing worth pinning down
here: exactly one offending record removed when identifiable, a safe
fallback to one-at-a-time otherwise, and never losing a record's result.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.hubspot_client.api import HubspotClient  # noqa: E402
from src.hubspot_client.config import Settings, TableConfig  # noqa: E402
from src.hubspot_client.write_api import (  # noqa: E402
    BATCH_MAX_RECORDS,
    HubspotWriteClient,
    UpsertRecord,
    _find_offending_record,
)


def _settings() -> Settings:
    return Settings(base_url="https://api.hubapi.com", api_key="fake-key", tables=[])


class _FakeResponse:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, responder):
        self._responder = responder
        self.requests = []

    def post(self, url, headers=None, json=None, timeout=None):
        self.requests.append(json)
        return self._responder(json)

    def get(self, *args, **kwargs):  # pragma: no cover - unused here
        raise NotImplementedError


# --------------------------------------------------------------------------------------
# fetch_table_with_ids vs fetch_table -- regression guard for the extraction path
# --------------------------------------------------------------------------------------


class _FakeReadSession:
    def __init__(self, payload):
        self._payload = payload

    def get(self, url, headers=None, params=None, timeout=None):
        return _FakeResponse(200, self._payload)


def test_fetch_table_with_ids_keeps_id_but_fetch_table_does_not():
    payload = {"results": [{"id": "123", "properties": {"email": "a@example.com"}}]}
    table = TableConfig(name="hubspot_contacts", object_type="contacts", fields=["email"])

    client = HubspotClient(settings=_settings(), session=_FakeReadSession(payload))
    assert client.fetch_table(table) == [{"email": "a@example.com"}]

    client2 = HubspotClient(settings=_settings(), session=_FakeReadSession(payload))
    with_ids = client2.fetch_table_with_ids(table)
    assert with_ids == [{"email": "a@example.com", "__hubspot_id": "123"}]


# --------------------------------------------------------------------------------------
# batch_upsert happy path
# --------------------------------------------------------------------------------------


def test_batch_upsert_maps_results_back_by_position():
    def responder(body):
        assert body["inputs"][0]["idProperty"] == "email"
        return _FakeResponse(
            200,
            {
                "results": [
                    {"id": "1", "new": True},
                    {"id": "2", "new": False},
                ]
            },
        )

    session = _FakeSession(responder)
    client = HubspotWriteClient(settings=_settings(), session=session)
    records = [
        UpsertRecord(id_value="a@example.com", properties={"firstname": "A"}),
        UpsertRecord(id_value="b@example.com", properties={"firstname": "B"}),
    ]

    results = {r.id_value: r for r in client.batch_upsert("contacts", "email", records)}

    assert results["a@example.com"].ok is True
    assert results["a@example.com"].hubspot_id == "1"
    assert results["a@example.com"].is_new is True
    assert results["b@example.com"].is_new is False


def test_batch_upsert_chunks_at_the_max_size():
    n = BATCH_MAX_RECORDS + 1
    records = [UpsertRecord(id_value=f"user{i}@example.com", properties={}) for i in range(n)]

    def responder(body):
        return _FakeResponse(200, {"results": [{"id": str(i), "new": True} for i in range(len(body["inputs"]))]})

    session = _FakeSession(responder)
    client = HubspotWriteClient(settings=_settings(), session=session)

    results = client.batch_upsert("contacts", "email", records)

    assert len(session.requests) == 2  # 100 + 1 -> two chunks
    assert len(results) == n
    assert all(r.ok for r in results)


# --------------------------------------------------------------------------------------
# Shrink-and-retry
# --------------------------------------------------------------------------------------


def test_shrink_and_retry_removes_only_the_identifiable_offender():
    calls = []

    def responder(body):
        calls.append([i["id"] for i in body["inputs"]])
        ids = [i["id"] for i in body["inputs"]]
        if "bad@example.com" in ids:
            return _FakeResponse(
                400,
                {
                    "message": "Property values were not valid for bad@example.com",
                    "category": "VALIDATION_ERROR",
                },
            )
        return _FakeResponse(200, {"results": [{"id": str(i), "new": True} for i in range(len(ids))]})

    session = _FakeSession(responder)
    client = HubspotWriteClient(settings=_settings(), session=session)
    records = [
        UpsertRecord(id_value="good1@example.com", properties={}),
        UpsertRecord(id_value="bad@example.com", properties={}),
        UpsertRecord(id_value="good2@example.com", properties={}),
    ]

    results = {r.id_value: r for r in client.batch_upsert("contacts", "email", records)}

    assert results["bad@example.com"].ok is False
    assert "not valid" in results["bad@example.com"].error_message
    assert results["good1@example.com"].ok is True
    assert results["good2@example.com"].ok is True
    # First call had all 3, second call retried the remaining 2 in one shot
    # (the offender was identifiable, so no need to fall back to size-1).
    assert len(calls) == 2
    assert len(calls[1]) == 2


def test_shrink_and_retry_falls_back_to_one_at_a_time_when_offender_unclear():
    def responder(body):
        if len(body["inputs"]) > 1:
            return _FakeResponse(400, {"message": "Something went wrong.", "category": "VALIDATION_ERROR"})
        # Single-record retry: only "bad@example.com" actually fails.
        record_id = body["inputs"][0]["id"]
        if record_id == "bad@example.com":
            return _FakeResponse(400, {"message": "still bad", "category": "VALIDATION_ERROR"})
        return _FakeResponse(200, {"results": [{"id": "1", "new": True}]})

    session = _FakeSession(responder)
    client = HubspotWriteClient(settings=_settings(), session=session)
    records = [
        UpsertRecord(id_value="good1@example.com", properties={}),
        UpsertRecord(id_value="bad@example.com", properties={}),
        UpsertRecord(id_value="good2@example.com", properties={}),
    ]

    results = {r.id_value: r for r in client.batch_upsert("contacts", "email", records)}

    assert len(results) == 3
    assert results["bad@example.com"].ok is False
    assert results["good1@example.com"].ok is True
    assert results["good2@example.com"].ok is True


def test_find_offending_record_returns_none_when_ambiguous():
    chunk = [
        UpsertRecord(id_value="a@example.com", properties={}),
        UpsertRecord(id_value="b@example.com", properties={}),
    ]
    # Both ids appear in the message -- can't pick one safely.
    body = {"message": "a@example.com and b@example.com both failed"}
    assert _find_offending_record(chunk, body) is None


def test_find_offending_record_uses_context_ids_when_present():
    chunk = [
        UpsertRecord(id_value="a@example.com", properties={}),
        UpsertRecord(id_value="b@example.com", properties={}),
    ]
    body = {"message": "validation failed", "context": {"ids": ["b@example.com"]}}
    offender = _find_offending_record(chunk, body)
    assert offender is not None
    assert offender.id_value == "b@example.com"


def test_batch_upsert_result_count_mismatch_is_reported_as_failure_not_a_crash():
    def responder(body):
        return _FakeResponse(200, {"results": [{"id": "1", "new": True}]})  # only 1, but 2 were sent

    session = _FakeSession(responder)
    client = HubspotWriteClient(settings=_settings(), session=session)
    records = [
        UpsertRecord(id_value="a@example.com", properties={}),
        UpsertRecord(id_value="b@example.com", properties={}),
    ]

    results = client.batch_upsert("contacts", "email", records)

    assert len(results) == 2
    assert all(not r.ok for r in results)
