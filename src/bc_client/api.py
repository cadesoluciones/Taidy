"""Business Central API wrapper."""

import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import requests
from requests import Response, Session

from .auth import TokenProvider
from .config import Settings

logger = logging.getLogger(__name__)


class BusinessCentralError(RuntimeError):
    """Raised when a Business Central request or response is invalid."""


class BusinessCentralClient:
    def __init__(
        self,
        *,
        settings: Settings,
        token_provider: TokenProvider,
        session: Optional[Session] = None,
        timeout: float = 30.0,
    ) -> None:
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
        Fetch all rows for the given table URL, following pagination.

        Returns:
            A list of dicts, one per row.
        """
        table_name = label or table_url
        all_rows: List[Dict[str, Any]] = []

        logger.info("Fetching rows for table '%s'...", table_name)

        page_number = 1
        url: Optional[str] = table_url

        while url:
            if page_number == 1 or page_number % progress_every_pages == 0:
                logger.info("Table '%s': fetched %d page(s)", table_name, page_number)

            payload = self._fetch_page(url)
            rows = self._read_rows(payload, url)
            all_rows.extend(rows)

            url = self._next_page_url(payload, url)
            page_number += 1

        logger.info(
            "Finished fetching rows for table '%s' (%d pages, %d rows).",
            table_name,
            page_number - 1,
            len(all_rows),
        )
        return all_rows

    # -------------------------
    # Page fetching / parsing
    # -------------------------

    def _fetch_page(self, url: str) -> Dict[str, Any]:
        """GET one page and return decoded JSON."""
        response = self._get(url)

        try:
            return response.json()
        except ValueError as exc:
            logger.exception("Failed to decode JSON response from %s", url)
            raise BusinessCentralError(
                f"Response from {url} was not valid JSON"
            ) from exc

    def _get(self, url: str) -> Response:
        """Low-level GET with auth + error checking."""
        token = self._token_provider.get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Prefer": f"odata.maxpagesize={self._page_size}",
        }

        logger.debug("GET %s (page size: %s)", url, self._page_size)
        response = self._session.get(url, headers=headers, timeout=self._timeout)

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
        """Extract the 'value' list and validate row types."""
        raw = payload.get("value", [])

        if not isinstance(raw, list):
            raise BusinessCentralError(
                f"Unexpected response from {url}: 'value' should be a list"
            )

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
        """Return next page URL if present, else None."""
        next_link = payload.get("@odata.nextLink")

        if not next_link:
            return None
        if not isinstance(next_link, str):
            raise BusinessCentralError(
                f"Unexpected pagination link from {current_url}: "
                "'@odata.nextLink' must be a string"
            )

        return urljoin(current_url, next_link)
