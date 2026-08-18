# -*- coding: utf-8 -*-
"""
src/bc_client/write_api.py -- the request is multipart/mixed, but BC's
*response* to a $batch call is the OData v4.01 JSON batch format
(`{"responses": [{"id", "status", "body"}, ...]}`), confirmed live against a
real BC sandbox -- an earlier version of this module assumed a multipart
response too and silently misread every successful write as "no response
part found". `test_parse_batch_response_matches_the_real_bc_response_shape`
pins the exact shape captured live so this regression can't come back.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.bc_client.write_api import (  # noqa: E402
    BATCH_MAX_OPERATIONS,
    BusinessCentralWriteClient,
    BusinessCentralWriteError,
    WriteOperation,
    _batch_url_for,
    _build_batch_body,
    _entity_url,
    _parse_batch_response,
)


class _FakeResponse:
    def __init__(self, content_type: str, content: bytes, status_code: int = 200):
        self.headers = {"Content-Type": content_type}
        self.content = content
        self.status_code = status_code
        self.text = content.decode("utf-8", errors="replace")

    def json(self):
        import json

        return json.loads(self.text)


def _json_batch_response(*items: tuple) -> bytes:
    """`items` is (content_id, status_code, body) tuples -- mirrors BC's real
    `{"responses": [{"id": "1", "status": 200, "body": {...}}, ...]}` shape."""
    responses = [{"id": str(content_id), "status": status, "body": body} for content_id, status, body in items]
    return json.dumps({"responses": responses}).encode("utf-8")


# --------------------------------------------------------------------------------------
# URL helpers
# --------------------------------------------------------------------------------------


def test_entity_url_preserves_query_string():
    url = _entity_url("https://api.example/contacts?company=CADE", "guid-123")
    assert url == "https://api.example/contacts(guid-123)?company=CADE"


def test_entity_url_without_query_string():
    assert _entity_url("https://api.example/contacts", "guid-123") == "https://api.example/contacts(guid-123)"


def test_batch_url_for_strips_last_path_segment_and_query():
    url = _batch_url_for("https://api.example/api/cade/CRM/v1.0/contacts?company=CADE")
    assert url == "https://api.example/api/cade/CRM/v1.0/$batch"


# --------------------------------------------------------------------------------------
# Request building
# --------------------------------------------------------------------------------------


def test_build_batch_body_includes_one_changeset_per_operation():
    ops = [
        WriteOperation(content_id=1, method="POST", body={"name": "Alice"}),
        WriteOperation(content_id=2, method="PATCH", body={"name": "Bob"}, system_id="guid-2", etag='W/"abc"'),
    ]
    body, content_type = _build_batch_body("https://api.example/contacts?company=X", ops)
    text = body.decode("utf-8")

    assert content_type.startswith("multipart/mixed; boundary=batch_")
    assert text.count("Content-Type: multipart/mixed; boundary=changeset_") == 2
    assert "POST https://api.example/contacts?company=X HTTP/1.1" in text
    assert "PATCH https://api.example/contacts(guid-2)?company=X HTTP/1.1" in text
    assert 'If-Match: W/"abc"' in text
    assert text.count("If-Match:") == 1  # only the PATCH gets one
    assert '{"name": "Alice"}' in text
    assert "Content-ID: 1" in text and "Content-ID: 2" in text


def test_build_batch_body_requires_etag_for_patch():
    ops = [WriteOperation(content_id=1, method="PATCH", body={}, system_id="guid-1", etag=None)]
    with pytest.raises(BusinessCentralWriteError, match="ETag"):
        _build_batch_body("https://api.example/contacts", ops)


# --------------------------------------------------------------------------------------
# Response parsing
# --------------------------------------------------------------------------------------


def test_parse_batch_response_handles_mixed_success_and_failure():
    response = _FakeResponse(
        "application/json",
        _json_batch_response(
            (1, 201, {"id": "new-guid-1", "name": "Alice"}),
            (2, 412, {"error": {"code": "PreconditionFailed", "message": "changed"}}),
        ),
    )
    ops = [
        WriteOperation(content_id=1, method="POST", body={}),
        WriteOperation(content_id=2, method="PATCH", body={}, system_id="guid-2", etag='W/"abc"'),
    ]

    results = {r.content_id: r for r in _parse_batch_response(response, ops)}

    assert results[1].ok is True
    assert results[1].status_code == 201
    assert results[1].body == {"id": "new-guid-1", "name": "Alice"}

    assert results[2].ok is False
    assert results[2].status_code == 412
    assert results[2].error_message == "changed"


def test_parse_batch_response_flags_a_missing_part_as_failed():
    response = _FakeResponse("application/json", _json_batch_response((1, 200, {"id": "guid-1"})))
    ops = [WriteOperation(content_id=1, method="POST", body={}), WriteOperation(content_id=2, method="POST", body={})]

    results = {r.content_id: r for r in _parse_batch_response(response, ops)}

    assert results[1].ok is True
    assert results[2].ok is False
    assert results[2].status_code == 0
    assert "No response part found" in results[2].error_message


def test_parse_batch_response_matches_the_real_bc_response_shape():
    """Literal fixture captured live against SANDBOX_CADE (see the module
    docstring) -- BC's $batch response includes extra keys (atomicityGroup,
    headers) that must be tolerated, not just the minimal id/status/body."""
    raw = (
        b'{"responses":[{"id":"1","atomicityGroup":"28033e3b-f2ba-47f0-a42d-ed51a0eb0255","status":200,'
        b'"headers":{"content-type":"application/json; odata.metadata=minimal","odata-version":"4.0"},'
        b'"body":{"@odata.etag":"W/\\"abc\\"","id":"471baf9a-feae-ed11-9a88-002248a2ef4d",'
        b'"email":"admon@aplitecgrupo.es","hubspotId":"hs-123"}}]}'
    )
    response = _FakeResponse("application/json", raw)
    ops = [WriteOperation(content_id=1, method="PATCH", body={}, system_id="x", etag='W/"abc"')]

    results = {r.content_id: r for r in _parse_batch_response(response, ops)}

    assert results[1].ok is True
    assert results[1].status_code == 200
    assert results[1].body["hubspotId"] == "hs-123"


def test_parse_batch_response_extracts_error_message_from_bc_404_shape():
    """Literal fixture from the actual 404 hit while diagnosing the wrong
    key-field-name bug: `(None)` in the URL -> 'Error in query syntax'."""
    raw = (
        b'{"responses":[{"id":"1","atomicityGroup":"e752ee73-3390-4ea5-ae1a-8da29980beed","status":404,'
        b'"headers":{"content-type":"application/json; charset=utf-8"},'
        b'"body":{"error":{"code":"BadRequest_NotFound","message":"Bad Request - Error in query syntax."}}}]}'
    )
    response = _FakeResponse("application/json", raw)
    ops = [WriteOperation(content_id=1, method="PATCH", body={}, system_id="x", etag='W/"abc"')]

    results = {r.content_id: r for r in _parse_batch_response(response, ops)}

    assert results[1].ok is False
    assert results[1].status_code == 404
    assert results[1].error_message == "Bad Request - Error in query syntax."


# --------------------------------------------------------------------------------------
# Client-level behavior (fake session, no network)
# --------------------------------------------------------------------------------------


class _FakeTokenProvider:
    def get_access_token(self) -> str:
        return "fake-token"


class _FakeSession:
    def __init__(self, get_responses=None, post_response=None):
        self._get_responses = get_responses or []
        self._post_response = post_response
        self.post_calls = []
        self.get_calls = []

    def get(self, url, headers=None, timeout=None):
        self.get_calls.append(url)
        return self._get_responses.pop(0)

    def post(self, url, data=None, headers=None, timeout=None):
        self.post_calls.append((url, data, headers))
        return self._post_response


def test_batch_write_chunks_operations_at_the_max_size():
    n = BATCH_MAX_OPERATIONS + 1
    ops = [WriteOperation(content_id=i, method="POST", body={"i": i}) for i in range(n)]

    def _fake_response_for(chunk):
        items = [(op.content_id, 200, {}) for op in chunk]
        return _FakeResponse("application/json", _json_batch_response(*items))

    session = _FakeSession()
    call_count = {"n": 0}

    def fake_post(url, data=None, headers=None, timeout=None):
        call_count["n"] += 1
        # Parse how many changesets are in this request by counting POST lines.
        chunk_size = data.decode("utf-8").count("POST https://api.example/contacts HTTP/1.1")
        chunk = ops[: chunk_size] if call_count["n"] == 1 else ops[BATCH_MAX_OPERATIONS:]
        return _fake_response_for(chunk)

    session.post = fake_post
    client = BusinessCentralWriteClient(token_provider=_FakeTokenProvider(), session=session)

    results = client.batch_write("https://api.example/contacts", ops)

    assert call_count["n"] == 2  # 20 + 1 -> two chunks
    assert len(results) == n
    assert all(r.ok for r in results)


def test_read_row_with_etag_returns_none_when_not_found():
    session = _FakeSession(get_responses=[_FakeResponse("application/json", b'{"value": []}')])
    client = BusinessCentralWriteClient(token_provider=_FakeTokenProvider(), session=session)

    row, etag = client.read_row_with_etag("https://api.example/contacts", "email", "missing@example.com")

    assert row is None
    assert etag is None


def test_read_rows_with_etag_maps_each_key_to_its_row_and_etag():
    payload = (
        b'{"value": ['
        b'{"email": "a@example.com", "@odata.etag": "W/\\"1\\"", "name": "A"},'
        b'{"email": "b@example.com", "@odata.etag": "W/\\"2\\"", "name": "B"}'
        b"]}"
    )
    session = _FakeSession(get_responses=[_FakeResponse("application/json", payload)])
    client = BusinessCentralWriteClient(token_provider=_FakeTokenProvider(), session=session)

    found = client.read_rows_with_etag(
        "https://api.example/contacts", "email", ["a@example.com", "b@example.com", "missing@example.com"]
    )

    assert set(found) == {"a@example.com", "b@example.com"}
    assert found["a@example.com"][1] == 'W/"1"'
    assert found["b@example.com"][0]["name"] == "B"
