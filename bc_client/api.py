"""Business Central API wrapper."""

from __future__ import annotations

from typing import Any, Dict, Iterable
from urllib.parse import urljoin, urlparse, urlunparse, parse_qsl, urlencode

import requests
from requests import Response, Session

from bc_client.auth import TokenProvider
from bc_client.config import Settings


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

    def iter_table_rows(self, table_url: str) -> Iterable[Dict[str, Any]]:
        next_url: str | None = self._prepare_initial_url(table_url)

        while next_url:
            current_url = next_url
            response = self._request(current_url)
            payload = self._parse_response(response)
            rows = payload.get("value", [])

            if not isinstance(rows, list):
                raise RuntimeError("Unexpected Business Central response: 'value' not a list")

            for row in rows:
                if isinstance(row, dict):
                    yield row
                else:
                    raise RuntimeError("Unexpected row format returned by Business Central")

            next_link = payload.get("@odata.nextLink")
            if isinstance(next_link, str) and next_link:
                next_url = urljoin(current_url, next_link)
            else:
                next_url = None

    def _request(self, url: str) -> Response:
        token = self._token_provider.get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

        response = self._session.get(url, headers=headers, timeout=self._timeout)
        if response.status_code >= 400:
            raise RuntimeError(
                f"Business Central request failed with status {response.status_code}: {response.text}"
            )
        return response

    def _prepare_initial_url(self, url: str) -> str:
        parsed = urlparse(url)
        query_items = parse_qsl(parsed.query, keep_blank_values=True)
        has_top = any(key == "$top" for key, _ in query_items)
        if not has_top:
            query_items.append(("$top", str(self._page_size)))
        new_query = urlencode(query_items, doseq=True)
        return urlunparse(parsed._replace(query=new_query))

    def _parse_response(self, response: Response) -> Dict[str, Any]:
        try:
            return response.json()
        except ValueError as exc:
            raise RuntimeError("Failed to decode Business Central response") from exc
