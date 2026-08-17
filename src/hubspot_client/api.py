# -*- coding: utf-8 -*-
"""
API client for the HubSpot CRM v3 Objects API.

Fetches any object type declared in hubspot_tables.yaml (contacts,
companies, deals, ...) and returns only the declared property fields.
Full extraction only -- no date range, employee filter, or checkpoint-based
incremental mode (unlike Factorial).
"""

from typing import Any, Dict, List, Optional
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

_PAGE_SIZE = 100


# --------------------------------------------------------------------------------------
# Custom Exception
# --------------------------------------------------------------------------------------


class HubspotError(RuntimeError):
    """Raised for HubSpot API-specific errors."""


class HubspotServerError(HubspotError):
    """Raised for 5xx/429 responses — transient, eligible for retry."""


# --------------------------------------------------------------------------------------
# API Client
# --------------------------------------------------------------------------------------


class HubspotClient:
    """
    Client for the HubSpot CRM v3 Objects API.

    Uses Bearer token authentication (Private App access token).
    Object type and field filters are driven by TableConfig entries.
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

    def fetch_table(self, table: TableConfig) -> List[Dict[str, Any]]:
        """Fetches every record for a TableConfig's object type, paginating to the end."""
        url = f"{self._settings.base_url}/crm/v3/objects/{table.object_type}"
        base_params: List[tuple] = [
            ("limit", str(_PAGE_SIZE)),
            ("properties", ",".join(table.fields)),
        ]

        logger.info("Fetching '%s'...", table.name)

        all_records: List[Dict[str, Any]] = []
        after: Optional[str] = None
        page = 1
        while True:
            params = base_params + ([("after", after)] if after else [])
            payload = self._fetch(url, params)
            all_records.extend(self._parse_data(payload, url, table.fields))

            after = payload.get("paging", {}).get("next", {}).get("after")
            if not after:
                break
            page += 1
            logger.info("'%s': fetching page %d (after=%s)...", table.name, page, after)

        logger.info("'%s': %d record(s) across %d page(s).", table.name, len(all_records), page)
        return all_records

    def fetch_all_tables(self) -> Dict[str, List[Dict[str, Any]]]:
        """Fetches all tables declared in settings, keyed by table name."""
        return {table.name: self.fetch_table(table) for table in self._settings.tables}

    def ping(self, object_type: str = "contacts") -> Dict[str, Any]:
        """Minimal read-only connectivity check: GET 1 record of the given object type."""
        url = f"{self._settings.base_url}/crm/v3/objects/{object_type}"
        return self._fetch(url, [("limit", "1")])

    # ----------------------------------------------------------------------------------
    # Internal helpers
    # ----------------------------------------------------------------------------------

    @retry(
        retry=retry_if_exception_type(
            (requests.ConnectionError, requests.Timeout, ChunkedEncodingError, HubspotServerError)
        ),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    def _fetch(self, url: str, params: List[tuple]) -> Dict[str, Any]:
        """GET request with Bearer auth, retries on transient errors and rate limiting."""
        headers = {
            "accept": "application/json",
            "authorization": f"Bearer {self._settings.api_key}",
        }

        logger.debug("GET %s?%s", url, urlencode(params))

        try:
            response: Response = self._session.get(
                url, headers=headers, params=params, timeout=self._timeout
            )
        except (requests.ConnectionError, requests.Timeout, ChunkedEncodingError) as exc:
            logger.warning("Network error on GET %s, will retry: %s", url, exc)
            raise

        if response.status_code == 429 or response.status_code >= 500:
            message = (
                f"HubSpot request failed ({response.status_code}) for {url}: "
                f"{response.text}"
            )
            logger.warning("%s — will retry", message)
            raise HubspotServerError(message)

        if response.status_code >= 400:
            message = (
                f"HubSpot request failed ({response.status_code}) for {url}: "
                f"{response.text}"
            )
            logger.error(message)
            raise HubspotError(message)

        try:
            return response.json()
        except ValueError as exc:
            raise HubspotError(f"Response from {url} was not valid JSON") from exc

    @staticmethod
    def _parse_data(
        payload: Dict[str, Any],
        url: str,
        fields: List[str],
    ) -> List[Dict[str, Any]]:
        """Extracts 'results' list and flattens each record's declared properties."""
        raw = payload.get("results", [])

        if not isinstance(raw, list):
            raise HubspotError(
                f"Unexpected response from {url}: 'results' should be a list"
            )

        records: List[Dict[str, Any]] = []
        for record in raw:
            if not isinstance(record, dict):
                continue
            properties = record.get("properties") or {}
            records.append({f: properties.get(f) for f in fields})
        return records
