"""Business Central API wrapper."""

import logging
import sys
from typing import Any, Dict, Iterable, Optional
from urllib.parse import urljoin

import requests
from requests import Response, Session

from .auth import TokenProvider
from .config import Settings

logger = logging.getLogger(__name__)


class BusinessCentralClient:
    def __init__(
        self,
        *,
        settings: Settings,
        token_provider: TokenProvider,
        session: Session | None,
        timeout: float,
    ) -> None:
        self._settings = settings
        self._token_provider = token_provider
        self._session = session or requests.Session()
        self._timeout = timeout
        self._page_size = settings.page_size

    def iter_table_rows(
        self, table_url: str, *, label: Optional[str] = None
    ) -> Iterable[Dict[str, Any]]:
        next_url: str | None = table_url

        pages = 0
        display_label = label or table_url

        logger.info(
            "Fetching rows for table '%s' (pagination progress shown as dots)",
            display_label,
        )

        while next_url:
            current_url = next_url
            pages += 1
            if logger.isEnabledFor(logging.INFO):
                sys.stdout.write(".")
                sys.stdout.flush()
            response = self._request(current_url)
            payload = self._parse_response(response)
            rows = payload.get("value", [])

            logger.debug(
                "Received %s rows from %s",
                len(rows) if isinstance(rows, list) else "unknown",
                current_url,
            )
            if not isinstance(rows, list):
                raise RuntimeError(
                    "Unexpected Business Central response: 'value' not a list"
                )

            for row in rows:
                if isinstance(row, dict):
                    yield row
                else:
                    raise RuntimeError(
                        "Unexpected row format returned by Business Central"
                    )

            next_link = payload.get("@odata.nextLink")
            if isinstance(next_link, str) and next_link:
                next_url = urljoin(current_url, next_link)
                logger.debug(
                    "Detected pagination next link, continuing with %s", next_url
                )
            else:
                next_url = None
                if pages:
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                logger.info(
                    "Pagination complete for table '%s' (%s pages)",
                    display_label,
                    pages,
                )

    def _request(self, url: str) -> Response:
        token = self._token_provider.get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Prefer": f"odata.maxpagesize={self._page_size}",
        }

        logger.debug(
            "Calling Business Central GET %s (page size %s)", url, self._page_size
        )
        response = self._session.get(url, headers=headers, timeout=self._timeout)
        logger.debug("Business Central response status %s", response.status_code)
        if response.status_code >= 400:
            raise RuntimeError(
                f"Business Central request failed with status {response.status_code}: {response.text}"
            )
        return response

    def _parse_response(self, response: Response) -> Dict[str, Any]:
        try:
            return response.json()
        except ValueError as exc:
            logger.exception("Failed to decode Business Central response")
            raise RuntimeError("Failed to decode Business Central response") from exc
