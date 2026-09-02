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

# HubSpot has no API to enumerate its own *standard* CRM objects -- unlike
# custom objects, they're a fixed part of the platform, not portal-specific
# configuration, so this list is as close to "discoverable" as they get.
# Whether a given one is actually usable still depends on the portal's Hub
# subscription (e.g. "tickets" needs Service Hub) -- list_object_types()
# doesn't try to verify that; a disabled object just 404s/403s later when
# something actually reads it.
STANDARD_OBJECT_TYPES: List[Dict[str, str]] = [
    {"name": "contacts", "label": "Contactos"},
    {"name": "companies", "label": "Empresas"},
    {"name": "deals", "label": "Negocios"},
    {"name": "tickets", "label": "Tickets"},
    {"name": "products", "label": "Productos"},
    {"name": "line_items", "label": "Líneas de producto"},
    {"name": "quotes", "label": "Presupuestos"},
    {"name": "calls", "label": "Llamadas"},
    {"name": "emails", "label": "Correos"},
    {"name": "meetings", "label": "Reuniones"},
    {"name": "notes", "label": "Notas"},
    {"name": "tasks", "label": "Tareas"},
]


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
        return self._fetch_table(table, include_id=False)

    def fetch_table_with_ids(self, table: TableConfig) -> List[Dict[str, Any]]:
        """Same as `fetch_table`, but each record also carries HubSpot's own
        record id under the reserved key `"__hubspot_id"` -- needed by the
        sync write phase to address an existing HubSpot record for update,
        or to write a newly-created record's id back into Business Central.
        `fetch_table` itself is unchanged so the extraction/Fabric upload
        path never sees this extra key."""
        return self._fetch_table(table, include_id=True)

    def _fetch_table(self, table: TableConfig, *, include_id: bool) -> List[Dict[str, Any]]:
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
            all_records.extend(self._parse_data(payload, url, table.fields, include_id=include_id))

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

    def search_table_with_ids(
        self, table: TableConfig, *, date_field: str, modified_since_epoch_ms: int
    ) -> List[Dict[str, Any]]:
        """Like `fetch_table_with_ids`, but only records whose `date_field`
        property is strictly greater than `modified_since_epoch_ms` -- used
        for the sync engine's incremental fetch (src/sync_engine/compare.py).

        Uses `POST /crm/v3/objects/{type}/search` (not the plain list
        endpoint `fetch_table` uses) since only Search supports filtering.
        HubSpot's Search API requires date-type filter *values* in epoch
        milliseconds, not the ISO-8601 string the same property returns from
        a normal read -- this is a real, easy-to-get-wrong assumption;
        see tests/test_hubspot_search_api.py for the live-verified shape.

        Also confirmed live: the Search API's index lags a few seconds
        behind a plain GET after a write (observed ~5s) -- a record edited
        just before this call may not appear yet even though it already
        exists. Acceptable for the read-only "Comparar" preview this feeds
        (src/sync_engine/compare.py); the real write phase never relies on
        it -- apply_mapping always compares with force_full=True, which
        reads HubSpot through the plain list endpoint (fetch_table_with_ids)
        instead, so it is unaffected by this lag.
        """
        url = f"{self._settings.base_url}/crm/v3/objects/{table.object_type}/search"
        base_body: Dict[str, Any] = {
            "filterGroups": [
                {"filters": [{"propertyName": date_field, "operator": "GT", "value": str(modified_since_epoch_ms)}]}
            ],
            "sorts": [{"propertyName": date_field, "direction": "ASCENDING"}],
            "properties": table.fields,
            "limit": _PAGE_SIZE,
        }

        logger.info("Searching '%s' for records modified since %s...", table.name, modified_since_epoch_ms)

        all_records: List[Dict[str, Any]] = []
        after: Optional[str] = None
        page = 1
        while True:
            body = dict(base_body, **({"after": after} if after else {}))
            payload = self._search(url, body)
            all_records.extend(self._parse_data(payload, url, table.fields, include_id=True))

            after = payload.get("paging", {}).get("next", {}).get("after")
            if not after:
                break
            page += 1
            logger.info("'%s': fetching page %d (after=%s)...", table.name, page, after)

        logger.info("'%s': %d record(s) modified since watermark, across %d page(s).", table.name, len(all_records), page)
        return all_records

    def list_properties(self, object_type: str, *, include_hidden: bool = False) -> List[Dict[str, Any]]:
        """Live discovery of every property HubSpot exposes for a CRM object
        type -- lets the admin UI show a pickable list instead of requiring
        someone to already know HubSpot's internal property names by heart.
        Unlike fetch_table/search_table_with_ids, this takes a raw
        object_type string rather than a TableConfig, so it works before a
        table entry has even been saved to hubspot_tables.yaml.

        `include_hidden=False` (the default) drops properties HubSpot itself
        marks as hidden or calculated -- mostly internal/derived noise not
        useful to extract -- since standard objects like contacts/companies
        can otherwise return hundreds of properties.
        """
        url = f"{self._settings.base_url}/crm/v3/properties/{object_type}"
        payload = self._fetch(url, [])
        results = payload.get("results", [])
        if not isinstance(results, list):
            raise HubspotError(f"Unexpected response from {url}: 'results' should be a list")

        properties = [
            {
                "name": r["name"],
                "label": r.get("label") or "",
                "hidden": bool(r.get("hidden")),
                "calculated": bool(r.get("calculated")),
                # HubSpot's own type vocabulary (string/number/date/datetime/
                # enumeration/bool/phone_number/json/...) -- kept as-is here,
                # not translated to anything else. webapp/fabric_catalog.py's
                # suggest_manual_columns() is the one place that maps this to
                # the semantic model's own MANUAL_DATA_TYPES.
                "type": r.get("type") or "",
            }
            for r in results
            if isinstance(r, dict) and r.get("name")
        ]
        if not include_hidden:
            properties = [p for p in properties if not p["hidden"] and not p["calculated"]]
        return sorted(properties, key=lambda p: p["name"])

    def list_object_types(self) -> List[Dict[str, str]]:
        """Every CRM object type this portal could plausibly extract from --
        for the admin UI's "available object types" helper, so a new
        hubspot_tables.yaml entry doesn't require already knowing HubSpot's
        object type names by heart.

        Always includes STANDARD_OBJECT_TYPES (fixed, not discoverable via
        API -- see its docstring). Also tries `GET /crm/v3/schemas` to add
        this portal's custom objects; that call needs a scope
        (crm.schemas.custom.read or similar) this project's Private App may
        not have been granted -- confirmed live to 403 without it -- so a
        failure here is swallowed rather than breaking the whole picker: the
        standard list alone is still useful.
        """
        types = list(STANDARD_OBJECT_TYPES)
        try:
            payload = self._fetch(f"{self._settings.base_url}/crm/v3/schemas", [])
        except HubspotError:
            logger.info("Could not list custom object schemas (likely missing scope) -- standard objects only.")
            return types

        for schema in payload.get("results", []) or []:
            if not isinstance(schema, dict):
                continue
            name = schema.get("fullyQualifiedName") or schema.get("objectTypeId") or schema.get("name")
            if not name:
                continue
            label = (schema.get("labels") or {}).get("plural") or schema.get("name") or name
            types.append({"name": name, "label": label})
        return types

    # ----------------------------------------------------------------------------------
    # Internal helpers
    # ----------------------------------------------------------------------------------

    def _raise_for_status(self, response: Response, url: str) -> None:
        if response.status_code == 429 or response.status_code >= 500:
            message = f"HubSpot request failed ({response.status_code}) for {url}: {response.text}"
            logger.warning("%s — will retry", message)
            raise HubspotServerError(message)

        if response.status_code >= 400:
            message = f"HubSpot request failed ({response.status_code}) for {url}: {response.text}"
            logger.error(message)
            raise HubspotError(message)

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

        self._raise_for_status(response, url)

        try:
            return response.json()
        except ValueError as exc:
            raise HubspotError(f"Response from {url} was not valid JSON") from exc

    @retry(
        retry=retry_if_exception_type(
            (requests.ConnectionError, requests.Timeout, ChunkedEncodingError, HubspotServerError)
        ),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    def _search(self, url: str, body: Dict[str, Any]) -> Dict[str, Any]:
        """POST request (CRM Search API) with Bearer auth, same retry/error
        shape as `_fetch`."""
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "authorization": f"Bearer {self._settings.api_key}",
        }

        logger.debug("POST %s (search)", url)

        try:
            response: Response = self._session.post(url, json=body, headers=headers, timeout=self._timeout)
        except (requests.ConnectionError, requests.Timeout, ChunkedEncodingError) as exc:
            logger.warning("Network error on POST %s, will retry: %s", url, exc)
            raise

        self._raise_for_status(response, url)

        try:
            return response.json()
        except ValueError as exc:
            raise HubspotError(f"Response from {url} was not valid JSON") from exc

    @staticmethod
    def _parse_data(
        payload: Dict[str, Any],
        url: str,
        fields: List[str],
        *,
        include_id: bool = False,
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
            row = {f: properties.get(f) for f in fields}
            if include_id:
                row["__hubspot_id"] = record.get("id")
            records.append(row)
        return records
