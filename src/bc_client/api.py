# -*- coding: utf-8 -*-
"""
A resilient API client for Microsoft Dynamics 365 Business Central.

This module provides a `BusinessCentralClient` that handles authentication,
automatic pagination for large datasets, and network resilience through
automatic retries with exponential backoff. It simplifies the process of
fetching all rows from a given OData endpoint.
"""

# --------------------------------------------------------------------------------------
# Imports
# --------------------------------------------------------------------------------------

from typing import Any, Dict, List, Optional
from urllib.parse import quote, urljoin

import requests
from requests import Response, Session
from requests.exceptions import ChunkedEncodingError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .auth import TokenProvider
from .config import _ENVIRONMENT_PLACEHOLDER, Settings
from ..config_loader import resolve_environment
from ..utils import get_logger

# --------------------------------------------------------------------------------------
# Constants and Global Variables
# --------------------------------------------------------------------------------------

logger = get_logger(__name__)


# --------------------------------------------------------------------------------------
# Custom Exceptions
# --------------------------------------------------------------------------------------


class BusinessCentralError(RuntimeError):
    """
    Custom exception raised for Business Central API-specific errors.

    This includes issues like malformed responses, unexpected status codes,
    or invalid data structures in the JSON payload.
    """


# --------------------------------------------------------------------------------------
# API Client
# --------------------------------------------------------------------------------------


class BusinessCentralClient:
    """
    A client for interacting with the Business Central OData API.

    This class encapsulates the logic for making authenticated requests, handling
    pagination via `@odata.nextLink`, and retrying failed network requests.
    """

    def __init__(
        self,
        *,
        settings: Settings,
        token_provider: TokenProvider,
        session: Optional[Session] = None,
        timeout: float = 30.0,
    ) -> None:
        """
        Initializes the Business Central client.

        Args:
            settings: The application settings, containing the API page size.
            token_provider: An object that can provide OAuth access tokens.
            session: An optional `requests.Session` object to use for making
                     HTTP requests. If not provided, a new one is created.
            timeout: The request timeout in seconds.
        """
        self._settings = settings
        self._token_provider = token_provider
        self._session = session or requests.Session()
        self._timeout = timeout
        self._page_size = settings.page_size

    def get_table_rows(
        self,
        table_url: str,
        *,
        label: Optional[str] = None,
        progress_every_pages: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Fetch all rows for a given table URL, automatically following pagination.

        This method repeatedly calls the API, following the `@odata.nextLink`
        provided in each response until all pages of data have been retrieved.

        Args:
            table_url: The initial URL of the OData endpoint for the table.
            label: A friendly name for the table, used for logging. If not
                   provided, the URL is used.
            progress_every_pages: How often to log progress (e.g., every 10 pages).

        Returns:
            A list of dictionaries, where each dictionary represents a row of data.
        """
        # Use a descriptive name for logging purposes.
        table_name = label or table_url
        all_rows: List[Dict[str, Any]] = []

        logger.info("Fetching rows for table '%s'...", table_name)

        # Loop through all pages using the OData `@odata.nextLink` for pagination.
        page_number = 1
        url: Optional[str] = table_url

        while url:
            # Log progress periodically to avoid spamming the console for large tables.
            if page_number == 1 or page_number % progress_every_pages == 0:
                logger.info(
                    "Table '%s': fetched %d page(s) so far", table_name, page_number
                )

            # Fetch the current page and extract its rows.
            payload = self._fetch_page(url)
            rows = self._read_rows(payload, url)
            all_rows.extend(rows)

            # The next URL is determined by the OData response. If it's missing,
            # we've reached the last page.
            url = self._next_page_url(payload, url)
            page_number += 1

        logger.info(
            "Finished fetching rows for table '%s' (%d pages, %d rows).",
            table_name,
            page_number - 1,
            len(all_rows),
        )
        return all_rows

    def list_available_tables(self) -> List[Dict[str, str]]:
        """Live discovery of every entity Business Central exposes, across
        BOTH mechanisms this project's tables use -- confirmed live against
        the real API:

        1. The standard OData v4 service root (.../ODataV4/) -- a plain GET
           returns every entity set, including every "APIxxxxx" custom page
           under its exact existing id (18/19 of this project's real,
           already-configured URLs matched byte-for-byte).
        2. BC's newer "Custom APIs" mechanism
           (.../api/{publisher}/{group}/{version}/...) -- each such GROUP's
           own root also responds with its own full service document (e.g.
           .../api/cade/Proyecto/v1.0/ listed 21 entities live, only one of
           which -- "recursos" -- was already tracked). There's no single
           endpoint listing every group across the whole tenant, though, so
           only groups already used by at least one currently-configured
           table are queried here -- an admin has to add one table from a
           brand-new group by hand once before its *other* entities become
           discoverable here too.

        Each returned "name" is the short, scannable entity id (prefixed
        with its group, for the Custom APIs ones, to tell same-named
        entities in different groups apart -- e.g. "Proyecto/recursos") --
        unlike HubSpot/Factorial, that's NOT the value to save here, since
        it's not a working URL by itself. "label" instead carries the
        FULL, ready-to-save URL, with the literal `{ENVIRONMENT}`
        placeholder tables.yaml itself uses (not this process's resolved
        value), so a picked entry's label can go straight into tables.yaml
        unchanged, same as every URL already there."""
        if not self._settings.tables:
            raise BusinessCentralError(
                "No hay ninguna tabla de Business Central configurada todavía -- hace falta al menos una "
                "para deducir el entorno y la empresa de la API."
            )

        environment = resolve_environment()
        company_literal = quote(self._settings.company_name.replace("'", "''"))
        company_query = quote(self._settings.company_name)
        tables: List[Dict[str, str]] = []

        odata_table = next((t for t in self._settings.tables if "/ODataV4/" in t.url), None)
        if odata_table is not None:
            prefix, _, _ = odata_table.url.partition("/ODataV4/")
            odata_root = f"{prefix}/ODataV4/"
            payload = self._fetch_page(odata_root)
            entries = payload.get("value", [])
            if not isinstance(entries, list):
                raise BusinessCentralError(f"Respuesta inesperada de {odata_root}: 'value' debería ser una lista")
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                name = entry.get("name")
                if not isinstance(name, str) or not name:
                    continue
                full_url = f"{odata_root}Company('{company_literal}')/{name}"
                full_url = full_url.replace(environment, _ENVIRONMENT_PLACEHOLDER, 1)
                tables.append({"name": name, "label": full_url})

        seen_groups: set = set()
        for table in self._settings.tables:
            if "/api/" not in table.url:
                continue
            prefix, _, rest = table.url.partition("/api/")
            segments = rest.split("/")
            if len(segments) < 4:
                continue
            publisher, group, version = segments[0], segments[1], segments[2]
            group_key = (prefix, publisher, group, version)
            if group_key in seen_groups:
                continue
            seen_groups.add(group_key)

            group_root = f"{prefix}/api/{publisher}/{group}/{version}/"
            try:
                payload = self._fetch_page(group_root)
            except (BusinessCentralError, requests.ConnectionError, requests.Timeout, ChunkedEncodingError) as exc:
                logger.warning("No se pudo listar el grupo de Custom APIs %s: %s", group_root, exc)
                continue
            entries = payload.get("value", [])
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                name = entry.get("name")
                if not isinstance(name, str) or not name:
                    continue
                full_url = f"{group_root}{name}?company={company_query}"
                full_url = full_url.replace(environment, _ENVIRONMENT_PLACEHOLDER, 1)
                tables.append({"name": f"{group}/{name}", "label": full_url})

        if not tables:
            raise BusinessCentralError("No se encontraron tablas disponibles en Business Central.")
        return sorted(tables, key=lambda t: t["name"])

    # ----------------------------------------------------------------------------------
    # Internal Page Fetching and Parsing
    # ----------------------------------------------------------------------------------

    def _fetch_page(self, url: str) -> Dict[str, Any]:
        """
        Fetches a single page of data and decodes its JSON payload.

        Args:
            url: The URL of the page to fetch.

        Returns:
            The parsed JSON payload as a dictionary.
        """
        response = self._get(url)

        try:
            return response.json()
        except ValueError as exc:
            logger.exception("Failed to decode JSON response from %s", url)
            raise BusinessCentralError(
                f"Response from {url} was not valid JSON"
            ) from exc

    # Decorator for automatic retries on specific, transient network errors.
    @retry(
        retry=retry_if_exception_type(
            (requests.ConnectionError, requests.Timeout, ChunkedEncodingError)
        ),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,  # Re-raise the exception if all retries fail.
    )
    def _get(self, url: str) -> Response:
        """
        Performs a low-level GET request with authentication and error handling.

        This method injects the OAuth token into the headers and sets the
        `odata.maxpagesize` preference. It also contains the core logic for
        handling HTTP status codes and raising appropriate errors.

        Args:
            url: The URL to GET.

        Returns:
            The `requests.Response` object.
        """
        token = self._token_provider.get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Prefer": f"odata.maxpagesize={self._page_size}",
        }

        logger.debug("GET %s (page size: %s)", url, self._page_size)

        try:
            response = self._session.get(url, headers=headers, timeout=self._timeout)
        except (
            requests.ConnectionError,
            requests.Timeout,
            ChunkedEncodingError,
        ) as exc:
            # This log is important for visibility when retries are happening.
            logger.warning("Network error on GET %s, will retry: %s", url, exc)
            raise

        # Check for client or server errors (4xx or 5xx).
        if response.status_code >= 400:
            message = (
                f"Business Central request failed "
                f"({response.status_code}) for {url}: {response.text}"
            )
            logger.error(message)
            raise BusinessCentralError(message)

        return response

    @staticmethod
    def _read_rows(payload: Dict[str, Any], url: str) -> List[Dict[str, Any]]:
        """
        Extracts the list of rows from the JSON payload and validates its structure.

        The rows are expected to be in a list under the 'value' key.

        Args:
            payload: The parsed JSON response from the API.
            url: The source URL, for inclusion in error messages.

        Returns:
            A list of rows, where each row is a dictionary.
        """
        raw = payload.get("value", [])

        if not isinstance(raw, list):
            raise BusinessCentralError(
                f"Unexpected response from {url}: 'value' should be a list"
            )

        # Validate that each item in the list is a dictionary.
        rows: List[Dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                raise BusinessCentralError(
                    f"Unexpected row format from {url}: each row must be an object"
                )
            rows.append(item)

        logger.debug("Received %d rows from %s", len(rows), url)
        return rows

    @staticmethod
    def _next_page_url(payload: Dict[str, Any], current_url: str) -> Optional[str]:
        """
        Extracts the next page URL from the OData pagination link.

        Args:
            payload: The parsed JSON response.
            current_url: The URL of the page just fetched, used as a base for
                         resolving relative next-links.

        Returns:
            The absolute URL for the next page, or `None` if it's the last page.
        """
        # The key for the next page link in OData is `@odata.nextLink`.
        next_link = payload.get("@odata.nextLink")

        if not next_link:
            return None
        if not isinstance(next_link, str):
            raise BusinessCentralError(
                f"Unexpected pagination link from {current_url}: "
                "'@odata.nextLink' must be a string"
            )

        # The `next_link` can be relative, so join it with the current URL
        # to ensure it's always an absolute URL.
        return urljoin(current_url, next_link)
