# -*- coding: utf-8 -*-
"""
A write client for the HubSpot CRM v3 Objects API, using the batch upsert
endpoint (`POST /crm/v3/objects/{objectType}/batch/upsert`) so a sync run
writes up to 100 records per HTTP call instead of one call per record.

Unlike Business Central's `$batch` (write_api.py in src/bc_client/), HubSpot's
batch endpoints are NOT true partial-failure: a single invalid input can fail
the whole call with no other input processed. `batch_upsert` compensates with
a "shrink and retry" loop -- see its docstring.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests
from requests.exceptions import ChunkedEncodingError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .api import HubspotError, HubspotServerError
from .config import Settings
from ..utils import get_logger

logger = get_logger(__name__)

# HubSpot's documented ceiling for objects/{type}/batch/upsert.
BATCH_MAX_RECORDS = 100


class HubspotWriteError(HubspotError):
    """Raised for write-specific failures not tied to a single record."""


class HubspotBatchError(HubspotWriteError):
    """A batch-level 4xx (excluding 429, which is retried as transient).
    Carries the parsed error body so the caller can try to identify which
    input caused it."""

    def __init__(self, body: Dict[str, Any]):
        self.body = body
        super().__init__(str(body.get("message") or body))


@dataclass
class UpsertRecord:
    """One record to upsert. `id_value` is the mapping's matching-key value
    on the HubSpot side (e.g. an email address), matched against
    `id_property`."""

    id_value: str
    properties: Dict[str, Any]


@dataclass
class UpsertResult:
    id_value: str
    ok: bool
    hubspot_id: Optional[str] = None
    is_new: Optional[bool] = None
    error_message: Optional[str] = None


class HubspotWriteClient:
    """Writes to HubSpot CRM objects via batch upsert."""

    def __init__(
        self,
        *,
        settings: Settings,
        session: Optional[requests.Session] = None,
        timeout: float = 60.0,
    ) -> None:
        self._settings = settings
        self._session = session or requests.Session()
        self._timeout = timeout

    def batch_upsert(
        self, object_type: str, id_property: str, records: List[UpsertRecord]
    ) -> List[UpsertResult]:
        """
        Upserts `records` (chunked to `BATCH_MAX_RECORDS`) into `object_type`,
        matching existing records by `id_property`.

        Returns one `UpsertResult` per input record, in no guaranteed order --
        match back to the request via `id_value`. A single problematic record
        never prevents the rest of `records` from being written.
        """
        results: List[UpsertResult] = []
        for i in range(0, len(records), BATCH_MAX_RECORDS):
            chunk = records[i : i + BATCH_MAX_RECORDS]
            results.extend(self._upsert_chunk_with_retry(object_type, id_property, chunk))
        return results

    def _upsert_chunk_with_retry(
        self, object_type: str, id_property: str, chunk: List[UpsertRecord]
    ) -> List[UpsertResult]:
        """
        Shrink-and-retry: on a batch-level error, try to identify exactly
        which input caused it (via the error body's `context.ids` or a
        substring match in its message) and remove only that one before
        resubmitting the rest. If the offending record can't be identified
        unambiguously, fall back to submitting the chunk one record at a
        time -- bounded, and guarantees one bad record never blocks its
        siblings (mirrors `FabricUploader`'s "never let one item kill the
        batch" applied to an API that doesn't naturally support it).
        """
        if not chunk:
            return []

        try:
            response = self._post_batch_upsert(object_type, id_property, chunk)
        except HubspotBatchError as exc:
            offending = _find_offending_record(chunk, exc.body)
            if offending is not None:
                remaining = [r for r in chunk if r is not offending]
                failed = UpsertResult(id_value=offending.id_value, ok=False, error_message=str(exc))
                return [failed] + self._upsert_chunk_with_retry(object_type, id_property, remaining)

            if len(chunk) == 1:
                return [UpsertResult(id_value=chunk[0].id_value, ok=False, error_message=str(exc))]

            logger.warning(
                "HubSpot batch upsert failed and the offending record couldn't be identified "
                "(%d records) -- retrying one at a time.",
                len(chunk),
            )
            results: List[UpsertResult] = []
            for record in chunk:
                results.extend(self._upsert_chunk_with_retry(object_type, id_property, [record]))
            return results

        return _zip_results(chunk, response)

    @retry(
        retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout, ChunkedEncodingError, HubspotServerError)),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    def _post_batch_upsert(
        self, object_type: str, id_property: str, chunk: List[UpsertRecord]
    ) -> Dict[str, Any]:
        url = f"{self._settings.base_url}/crm/v3/objects/{object_type}/batch/upsert"
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "authorization": f"Bearer {self._settings.api_key}",
        }
        body = {
            "inputs": [
                {"idProperty": id_property, "id": record.id_value, "properties": record.properties}
                for record in chunk
            ]
        }

        logger.debug("POST %s (%d record(s))", url, len(chunk))

        try:
            response = self._session.post(url, headers=headers, json=body, timeout=self._timeout)
        except (requests.ConnectionError, requests.Timeout, ChunkedEncodingError) as exc:
            logger.warning("Network error on POST %s, will retry: %s", url, exc)
            raise

        if response.status_code == 429 or response.status_code >= 500:
            message = f"HubSpot batch upsert failed ({response.status_code}) for {url}: {response.text}"
            logger.warning("%s — will retry", message)
            raise HubspotServerError(message)

        if response.status_code >= 400:
            try:
                error_body = response.json()
            except ValueError:
                error_body = {"message": response.text}
            raise HubspotBatchError(error_body)

        try:
            return response.json()
        except ValueError as exc:
            raise HubspotWriteError(f"Response from {url} was not valid JSON") from exc


def _zip_results(chunk: List[UpsertRecord], response: Dict[str, Any]) -> List[UpsertResult]:
    """Matches `response["results"]` back to `chunk` by position -- HubSpot's
    batch endpoints preserve input order in their output, and the response
    doesn't reliably echo back the original `idProperty` value per result."""
    raw_results = response.get("results", [])
    if len(raw_results) != len(chunk):
        message = (
            f"HubSpot devolvió {len(raw_results)} resultado(s) para {len(chunk)} "
            "registro(s) enviados -- no se puede emparejar con seguridad."
        )
        return [UpsertResult(id_value=r.id_value, ok=False, error_message=message) for r in chunk]

    return [
        UpsertResult(id_value=record.id_value, ok=True, hubspot_id=raw.get("id"), is_new=raw.get("new"))
        for record, raw in zip(chunk, raw_results)
    ]


def _find_offending_record(chunk: List[UpsertRecord], body: Dict[str, Any]) -> Optional[UpsertRecord]:
    """Best-effort identification of which input caused a batch-level error,
    from `context.ids` (a shape HubSpot uses for some validation errors) or a
    substring match of an `id_value` in the error message. Returns `None`
    (triggering the one-at-a-time fallback) unless exactly one record
    matches -- never guesses when it's ambiguous."""
    candidates: set = set()
    context = body.get("context")
    if isinstance(context, dict) and isinstance(context.get("ids"), list):
        candidates.update(str(v) for v in context["ids"])

    message = str(body.get("message", ""))
    matches = [r for r in chunk if r.id_value in candidates or r.id_value in message]
    return matches[0] if len(matches) == 1 else None
