# -*- coding: utf-8 -*-
"""
API client for Factorial HR endpoints.

Fetches any endpoint declared in factorial_tables.yaml and returns only
the fields specified per table.
"""

from datetime import date, timedelta
from typing import Any, Dict, Generator, List, Optional, Tuple
from urllib.parse import urlencode

import requests
from requests import Response, Session
from requests.exceptions import ChunkedEncodingError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .config import Settings, TableConfig
from ..utils import get_logger

# --------------------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------------------

logger = get_logger(__name__)

# How many records to inspect when peeking at a live sample to discover field
# names (sample_fields) -- enough to catch fields that don't appear on every
# single record, without turning a "just show me the fields" click into a
# full extraction.
_SAMPLE_SIZE = 20


# --------------------------------------------------------------------------------------
# Custom Exception
# --------------------------------------------------------------------------------------


class FactorialError(RuntimeError):
    """Raised for Factorial API-specific errors."""


class FactorialServerError(FactorialError):
    """Raised for 5xx responses — transient, eligible for retry."""


# --------------------------------------------------------------------------------------
# API Client
# --------------------------------------------------------------------------------------


class FactorialClient:
    """
    Client for the Factorial HR API.

    Uses x-api-key header authentication.
    Endpoint paths and field filters are driven by TableConfig entries.
    """

    def __init__(
        self,
        *,
        settings: Settings,
        session: Optional[Session] = None,
        timeout: float = 60.0,
    ) -> None:
        self._settings = settings
        self._session = session or requests.Session()
        self._timeout = timeout

    def fetch_table(
        self,
        table: TableConfig,
        *,
        start_on: str = "",
        end_on: str = "",
        employee_ids: Optional[List[int]] = None,
        extra_params: Optional[List[tuple]] = None,
    ) -> List[Dict[str, Any]]:
        """Fetches all data for a TableConfig, splitting into date chunks if configured."""
        if table.chunk_days and table.date_range and start_on and end_on:
            return self._fetch_chunked(
                table,
                start_on=start_on,
                end_on=end_on,
                employee_ids=employee_ids,
                extra_params=extra_params,
            )
        return self._fetch_window(
            table,
            start_on=start_on,
            end_on=end_on,
            employee_ids=employee_ids,
            extra_params=extra_params,
        )

    def _fetch_chunked(
        self,
        table: TableConfig,
        *,
        start_on: str,
        end_on: str,
        employee_ids: Optional[List[int]],
        extra_params: Optional[List[tuple]],
    ) -> List[Dict[str, Any]]:
        """Splits the date range into chunks and fetches each one sequentially."""
        start = date.fromisoformat(start_on)
        end = date.fromisoformat(end_on)
        chunks = list(_date_chunks(start, end, table.chunk_days))
        logger.info(
            "'%s': splitting %s → %s into %d chunk(s) of %d day(s).",
            table.name, start_on, end_on, len(chunks), table.chunk_days,
        )
        all_records: List[Dict[str, Any]] = []
        for i, (chunk_start, chunk_end) in enumerate(chunks, 1):
            logger.info(
                "'%s': chunk %d/%d — %s → %s.",
                table.name, i, len(chunks), chunk_start, chunk_end,
            )
            rows = self._fetch_window(
                table,
                start_on=chunk_start.isoformat(),
                end_on=chunk_end.isoformat(),
                employee_ids=employee_ids,
                extra_params=extra_params,
            )
            all_records.extend(rows)
        logger.info("'%s': %d total record(s) across %d chunk(s).", table.name, len(all_records), len(chunks))
        return all_records

    def _fetch_window(
        self,
        table: TableConfig,
        *,
        start_on: str = "",
        end_on: str = "",
        employee_ids: Optional[List[int]] = None,
        extra_params: Optional[List[tuple]] = None,
    ) -> List[Dict[str, Any]]:
        """Fetches a single date window with full cursor pagination."""
        version = table.version or self._settings.api_version
        url = f"{self._settings.base_url}/{version}/{table.path}"

        params: List[tuple[str, Any]] = []
        if table.date_range:
            params += [("start_on", start_on), ("end_on", end_on)]
        if table.employee_filter and employee_ids:
            for eid in employee_ids:
                params.append(("employee_ids[]", eid))
        if table.extra_params:
            params.extend(table.extra_params)
        if extra_params:
            params.extend(extra_params)

        _date_info = f" from {start_on} to {end_on}" if table.date_range else ""
        _emp_info = f" for {len(employee_ids or [])} employee(s)" if table.employee_filter else ""
        logger.info("Fetching '%s'%s%s.", table.name, _date_info, _emp_info)

        all_records: List[Dict[str, Any]] = []
        next_url: Optional[str] = url
        next_params: Optional[List[tuple]] = params
        seen_cursors: set = set()
        page = 1

        while next_url:
            payload = self._fetch(next_url, next_params or [])
            records = self._parse_data(payload, url, table.fields)
            all_records.extend(records)

            # Priority 1: OData-style next link (full URL, no extra params needed)
            odata_next = payload.get("@odata.nextLink")
            if odata_next:
                next_url = odata_next
                next_params = []
                page += 1
                logger.info("'%s': fetching page %d (odata.nextLink)...", table.name, page)
                continue

            # Priority 2: cursor-based meta pagination
            meta = payload.get("meta", {})
            if not meta.get("has_next_page"):
                break

            new_cursor = meta.get("end_cursor")
            if not new_cursor or new_cursor in seen_cursors:
                logger.warning(
                    "'%s': cursor did not advance after page %d — stopping pagination.",
                    table.name,
                    page,
                )
                break

            seen_cursors.add(new_cursor)
            next_url = url
            next_params = params + [("after_id", new_cursor)]
            page += 1
            logger.info("'%s': fetching page %d (cursor=%s)...", table.name, page, new_cursor)

        logger.info("'%s': %d record(s) across %d page(s).", table.name, len(all_records), page)
        return all_records

    def fetch_all_tables(
        self,
        *,
        start_on: str,
        end_on: str,
        employee_ids: List[int],
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Fetches all tables declared in settings, keyed by table name.

        Returns:
            Dict mapping table name → list of filtered records.
        """
        return {
            table.name: self.fetch_table(
                table,
                start_on=start_on,
                end_on=end_on,
                employee_ids=employee_ids,
            )
            for table in self._settings.tables
        }

    def sample_fields(self, *, path: str, date_range: bool = False, version: str = "") -> List[str]:
        """Live discovery of the field names a Factorial endpoint actually
        returns, for the admin UI's "available fields" helper. Factorial has
        no schema/properties endpoint like HubSpot's, so this is a
        best-effort peek: fetch one small page of real data and return the
        union of keys seen across up to _SAMPLE_SIZE records. It's meant to
        help pick fields when registering a new table, not a source of
        truth -- a field that's null/absent on every sampled record (or one
        that only appears once employee_ids are supplied, which this call
        never has) can be missed and would still need typing in by hand.
        """
        url = f"{self._settings.base_url}/{version or self._settings.api_version}/{path}"
        params: List[tuple] = []
        if date_range:
            today = date.today().isoformat()
            params += [("start_on", today), ("end_on", today)]

        payload = self._fetch(url, params)
        raw = payload.get("data", [])
        if not isinstance(raw, list):
            raise FactorialError(f"Unexpected response from {url}: 'data' should be a list")

        keys: set = set()
        for record in raw[:_SAMPLE_SIZE]:
            if isinstance(record, dict):
                keys.update(record.keys())
        return sorted(keys)

    def list_available_tables(self) -> List[Dict[str, str]]:
        """Live discovery of every readable endpoint Factorial's public API
        exposes, for the admin UI's "available tables" helper -- unlike
        sample_fields (which peeks at real data because there's no schema
        endpoint), Factorial *does* publish its full OpenAPI spec live at
        GET {domain}/oas/?version=..., confirmed to work even without
        authentication. Returns only GET "list" endpoints (no `{id}` path
        parameter -- e.g. `resources/ats/candidates`, not
        `resources/ats/candidates/{id}`), in the same relative-path shape
        TableConfig.path already expects.
        """
        base_root = self._settings.base_url.removesuffix("/api")
        url = f"{base_root}/oas/"
        spec = self._fetch(url, [("version", self._settings.api_version)])

        paths = spec.get("paths", {})
        if not isinstance(paths, dict):
            raise FactorialError(f"Unexpected response from {url}: 'paths' should be a mapping")

        prefix = f"/api/{self._settings.api_version}/"
        tables: List[Dict[str, str]] = []
        for path, methods in paths.items():
            if "{" in path or not isinstance(methods, dict) or "get" not in methods:
                continue
            relative = path[len(prefix):] if path.startswith(prefix) else path.lstrip("/")
            get_info = methods["get"] or {}
            tag = (get_info.get("tags") or [relative])[0]
            summary = get_info.get("summary") or ""
            label = f"{tag} — {summary}" if summary else tag
            tables.append({"name": relative, "label": label})
        return sorted(tables, key=lambda t: t["name"])

    # ----------------------------------------------------------------------------------
    # Internal helpers
    # ----------------------------------------------------------------------------------

    @retry(
        retry=retry_if_exception_type(
            (requests.ConnectionError, requests.Timeout, ChunkedEncodingError, FactorialServerError)
        ),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    def _fetch(self, url: str, params: List[tuple]) -> Dict[str, Any]:
        """GET request with x-api-key auth, retries on transient errors."""
        headers = {
            "accept": "application/json",
            "x-api-key": self._settings.api_key,
        }

        logger.debug("GET %s?%s", url, urlencode(params))

        try:
            response: Response = self._session.get(
                url, headers=headers, params=params, timeout=self._timeout
            )
        except (requests.ConnectionError, requests.Timeout, ChunkedEncodingError) as exc:
            logger.warning("Network error on GET %s, will retry: %s", url, exc)
            raise

        if response.status_code >= 400:
            message = (
                f"Factorial request failed ({response.status_code}) for {url}: "
                f"{response.text}"
            )
            if response.status_code >= 500:
                logger.warning("%s — will retry", message)
                raise FactorialServerError(message)
            logger.error(message)
            raise FactorialError(message)

        try:
            return response.json()
        except ValueError as exc:
            raise FactorialError(f"Response from {url} was not valid JSON") from exc

    @staticmethod
    def _parse_data(
        payload: Dict[str, Any],
        url: str,
        fields: List[str],
    ) -> List[Dict[str, Any]]:
        """Extracts 'data' list and filters to the declared fields."""
        raw = payload.get("data", [])

        if not isinstance(raw, list):
            raise FactorialError(
                f"Unexpected response from {url}: 'data' should be a list"
            )

        return [
            {f: record.get(f) for f in fields}
            for record in raw
            if isinstance(record, dict)
        ]


def _date_chunks(
    start: date, end: date, chunk_days: int
) -> Generator[Tuple[date, date], None, None]:
    """Yields (chunk_start, chunk_end) pairs covering [start, end] with no gaps."""
    current = start
    while current <= end:
        chunk_end = min(current + timedelta(days=chunk_days - 1), end)
        yield current, chunk_end
        current = chunk_end + timedelta(days=1)
