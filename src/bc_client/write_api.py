# -*- coding: utf-8 -*-
"""
A write client for the Business Central OData API, using `$batch` (multipart)
requests so that a single sync run can create/update many records in a
handful of HTTP calls instead of one call per record.

This is deliberately a separate class from `BusinessCentralClient` (api.py):
that client is read-only and has no notion of ETags, If-Match, or $batch --
mixing write concerns into it would blur a client that every extraction
pipeline depends on. This module only reuses `TokenProvider` from `auth.py`.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, Tuple
from urllib.parse import quote

import requests
from requests import Response, Session
from requests.exceptions import ChunkedEncodingError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .api import BusinessCentralError
from .auth import TokenProvider
from ..utils import get_logger

logger = get_logger(__name__)

# BC's documented practical ceiling on changesets per $batch call. Kept well
# under any hard server-side limit so a single request never risks a 413.
BATCH_MAX_OPERATIONS = 20

# How many key values to OR together in a single `$filter` when re-reading
# ETags in bulk -- keeps the resulting URL comfortably short.
ETAG_LOOKUP_CHUNK_SIZE = 20


class BusinessCentralWriteError(BusinessCentralError):
    """Raised for write-specific failures: a malformed $batch response, or a
    whole-batch HTTP failure that isn't a per-item error."""


@dataclass
class WriteOperation:
    """
    A single create or update to include in a `$batch` call.

    Attributes:
        content_id: Caller-assigned id (unique within one `batch_write` call)
                    used to match this operation back to its `WriteResult`.
        method: "POST" to create a new row, "PATCH" to update an existing one.
        system_id: The BC entity key (`SystemId`) being updated. Required for
                   PATCH, ignored for POST.
        etag: The `@odata.etag` to send as `If-Match`. Required for PATCH --
              always re-read fresh immediately before writing, never reused
              from an earlier read (see `read_rows_with_etag`).
        body: The JSON-serializable field values to send.
    """

    content_id: int
    method: Literal["POST", "PATCH"]
    body: Dict[str, Any]
    system_id: Optional[str] = None
    etag: Optional[str] = None


@dataclass
class WriteResult:
    """
    The outcome of one `WriteOperation` inside a `$batch` response.

    Attributes:
        content_id: Matches the originating `WriteOperation.content_id`.
        ok: True for a 2xx sub-response.
        status_code: The sub-response's HTTP status code.
        body: The created/updated entity on success (so a create's new
              `SystemId` can be read back), `None` otherwise.
        error_message: Human-readable failure reason, `None` on success.
    """

    content_id: int
    ok: bool
    status_code: int
    body: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None


class BusinessCentralWriteClient:
    """
    Writes to the Business Central OData API via `$batch` multipart requests.

    Each `WriteOperation` is wrapped in its own OData changeset so that one
    failing item never rolls back its siblings in the same call (an OData
    changeset is an atomic transaction -- grouping multiple operations into
    one changeset would mean a single failure fails all of them).
    """

    def __init__(
        self,
        *,
        token_provider: TokenProvider,
        session: Optional[Session] = None,
        timeout: float = 30.0,
    ) -> None:
        self._token_provider = token_provider
        self._session = session or requests.Session()
        self._timeout = timeout

    # ----------------------------------------------------------------------------------
    # Fresh ETag lookups -- writes must never reuse an ETag captured during an
    # earlier read (e.g. from `compare_mapping`'s snapshot), since the row may
    # have changed since then.
    # ----------------------------------------------------------------------------------

    def read_row_with_etag(
        self, table_url: str, key_field: str, key_value: str
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        Re-reads a single row by an arbitrary field and returns it with its
        current `@odata.etag`.

        Returns:
            `(row, etag)`, or `(None, None)` if no row matches.
        """
        results = self.read_rows_with_etag(table_url, key_field, [key_value])
        return results.get(key_value, (None, None))

    def read_rows_with_etag(
        self,
        table_url: str,
        key_field: str,
        key_values: List[str],
        *,
        chunk_size: int = ETAG_LOOKUP_CHUNK_SIZE,
    ) -> Dict[str, Tuple[Dict[str, Any], str]]:
        """
        Re-reads many rows by an arbitrary field, batching the lookups into
        `$filter=... or ...` chunks rather than one GET per key.

        Returns:
            A dict mapping each found key value to `(row, etag)`. Keys with
            no matching row are simply absent.
        """
        unique_values = list(dict.fromkeys(key_values))
        found: Dict[str, Tuple[Dict[str, Any], str]] = {}

        for i in range(0, len(unique_values), chunk_size):
            chunk = unique_values[i : i + chunk_size]
            filter_expr = " or ".join(f"{key_field} eq '{_escape_odata_literal(v)}'" for v in chunk)
            url = _add_query_param(table_url, "$filter", filter_expr)

            payload = self._get(url).json()
            for row in payload.get("value", []):
                etag = row.get("@odata.etag")
                value = row.get(key_field)
                if etag is not None and value is not None:
                    found[str(value)] = (row, etag)

        return found

    # ----------------------------------------------------------------------------------
    # $batch writes
    # ----------------------------------------------------------------------------------

    def batch_write(self, table_url: str, operations: List[WriteOperation]) -> List[WriteResult]:
        """
        Executes create/update operations against `table_url` via `$batch`,
        chunking into groups of `BATCH_MAX_OPERATIONS`.

        Args:
            table_url: The entity-set URL the operations target (the same
                       URL `tables.yaml` declares for this table).
            operations: The operations to execute. Every `content_id` must
                        be unique across the whole list.

        Returns:
            One `WriteResult` per operation, in no particular order --
            match back to the request via `content_id`.
        """
        results: List[WriteResult] = []
        batch_url = _batch_url_for(table_url)

        for i in range(0, len(operations), BATCH_MAX_OPERATIONS):
            chunk = operations[i : i + BATCH_MAX_OPERATIONS]
            body, content_type = _build_batch_body(table_url, chunk)
            response = self._post_batch(batch_url, body, content_type)
            results.extend(_parse_batch_response(response, chunk))

        return results

    @retry(
        retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout, ChunkedEncodingError)),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    def _post_batch(self, batch_url: str, body: bytes, content_type: str) -> Response:
        """
        Sends one `$batch` request. Retries only on transport-level failures
        of the *whole* request -- a per-item 4xx/412 inside a successfully
        delivered `$batch` response is never retried here, only surfaced as a
        failed `WriteResult` for the caller (`apply.py`) to decide on.
        """
        token = self._token_provider.get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": content_type,
        }

        logger.debug("POST %s ($batch, %d bytes)", batch_url, len(body))

        try:
            response = self._session.post(batch_url, data=body, headers=headers, timeout=self._timeout)
        except (requests.ConnectionError, requests.Timeout, ChunkedEncodingError) as exc:
            logger.warning("Network error on POST %s, will retry: %s", batch_url, exc)
            raise

        if response.status_code >= 400:
            message = f"Business Central $batch request failed ({response.status_code}) for {batch_url}: {response.text}"
            logger.error(message)
            raise BusinessCentralWriteError(message)

        return response

    @retry(
        retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout, ChunkedEncodingError)),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    def _get(self, url: str) -> Response:
        """Plain authenticated GET, same resilience/error shape as
        `BusinessCentralClient._get` (kept separate rather than shared since
        this client has no page-size/pagination concerns)."""
        token = self._token_provider.get_access_token()
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

        try:
            response = self._session.get(url, headers=headers, timeout=self._timeout)
        except (requests.ConnectionError, requests.Timeout, ChunkedEncodingError) as exc:
            logger.warning("Network error on GET %s, will retry: %s", url, exc)
            raise

        if response.status_code >= 400:
            message = f"Business Central request failed ({response.status_code}) for {url}: {response.text}"
            logger.error(message)
            raise BusinessCentralError(message)

        return response


# --------------------------------------------------------------------------------------
# URL helpers
# --------------------------------------------------------------------------------------


def _escape_odata_literal(value: str) -> str:
    """OData string literals escape a single quote by doubling it."""
    return value.replace("'", "''")


def _add_query_param(url: str, key: str, value: str) -> str:
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{key}={quote(value, safe='')}"


def _entity_url(table_url: str, system_id: str) -> str:
    """Builds `<collection>(<SystemId>)`, preserving any query string (e.g.
    `?company=...`) required by custom API pages."""
    base, _, query = table_url.partition("?")
    entity = f"{base.rstrip('/')}({system_id})"
    return f"{entity}?{query}" if query else entity


def _batch_url_for(table_url: str) -> str:
    """`$batch` lives at the service root, one path segment up from the
    entity set. ASSUMPTION, not yet verified against a live BC environment --
    see the implementation plan's risk notes."""
    base = table_url.partition("?")[0].rstrip("/")
    root = base.rsplit("/", 1)[0]
    return f"{root}/$batch"


# --------------------------------------------------------------------------------------
# $batch request (multipart/mixed) building and response parsing
#
# The request body is multipart/mixed (verified working against a real BC
# sandbox) -- but BC's *response* to that same request is NOT multipart: it's
# the OData v4.01 JSON batch format (`{"responses": [{"id", "status", "body"}
# , ...]}`), confirmed live against a real BC environment. An earlier version
# of this module assumed a multipart response too and silently failed every
# write with "No response part found" -- the write itself succeeded, only the
# result was misread as absent.
# --------------------------------------------------------------------------------------


def _build_batch_body(table_url: str, operations: List[WriteOperation]) -> Tuple[bytes, str]:
    """
    Builds an OData v4 `$batch` multipart body with one changeset per
    operation (see class docstring for why one-changeset-per-operation).
    """
    batch_boundary = f"batch_{uuid.uuid4().hex}"
    parts: List[str] = []

    for op in operations:
        changeset_boundary = f"changeset_{uuid.uuid4().hex}"
        url = table_url if op.method == "POST" else _entity_url(table_url, op.system_id)

        request_lines = [f"{op.method} {url} HTTP/1.1", "Content-Type: application/json"]
        if op.method == "PATCH":
            if not op.etag:
                raise BusinessCentralWriteError(f"PATCH operation (content_id={op.content_id}) is missing an ETag")
            request_lines.append(f"If-Match: {op.etag}")

        inner_request = "\r\n".join(request_lines) + "\r\n\r\n" + json.dumps(op.body)

        changeset = (
            f"--{changeset_boundary}\r\n"
            "Content-Type: application/http\r\n"
            "Content-Transfer-Encoding: binary\r\n"
            f"Content-ID: {op.content_id}\r\n"
            "\r\n"
            f"{inner_request}\r\n"
            f"--{changeset_boundary}--\r\n"
        )

        parts.append(
            f"--{batch_boundary}\r\n"
            f"Content-Type: multipart/mixed; boundary={changeset_boundary}\r\n"
            "\r\n"
            f"{changeset}"
        )

    body_text = "".join(parts) + f"--{batch_boundary}--\r\n"
    content_type = f"multipart/mixed; boundary={batch_boundary}"
    return body_text.encode("utf-8"), content_type


def _parse_batch_response(response: Response, operations: List[WriteOperation]) -> List[WriteResult]:
    """
    Parses BC's JSON `$batch` response body:

        {"responses": [{"id": "1", "status": 200, "body": {...}}, ...]}

    into one `WriteResult` per operation, matched by `id` (BC echoes back the
    `Content-ID` we sent as a string in this field).
    """
    by_content_id = {op.content_id: op for op in operations}

    try:
        payload = response.json()
    except ValueError as exc:
        raise BusinessCentralWriteError(f"$batch response was not valid JSON: {response.text[:500]}") from exc

    raw_responses = payload.get("responses")
    if not isinstance(raw_responses, list):
        raise BusinessCentralWriteError(f"$batch response missing a 'responses' list: {response.text[:500]}")

    results: List[WriteResult] = []
    seen_content_ids: set = set()

    for raw in raw_responses:
        try:
            content_id = int(raw.get("id"))
        except (TypeError, ValueError):
            continue

        status_code = raw.get("status") or 0
        body = raw.get("body")
        ok = 200 <= status_code < 300

        error_message = None
        if not ok:
            if isinstance(body, dict) and isinstance(body.get("error"), dict):
                error_message = body["error"].get("message") or str(body)
            else:
                error_message = str(body) if body else f"HTTP {status_code}"

        results.append(
            WriteResult(
                content_id=content_id,
                ok=ok,
                status_code=status_code,
                body=body if ok and isinstance(body, dict) else None,
                error_message=error_message,
            )
        )
        seen_content_ids.add(content_id)

    missing = set(by_content_id) - seen_content_ids
    for content_id in missing:
        results.append(
            WriteResult(
                content_id=content_id,
                ok=False,
                status_code=0,
                error_message="No response part found for this operation in the $batch response",
            )
        )

    return results
