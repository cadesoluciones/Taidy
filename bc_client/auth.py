"""Authentication helpers for Business Central API access."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional, Protocol

import requests
from requests import Response, Session


class TokenProvider(Protocol):
    def get_access_token(self) -> str:  # pragma: no cover - interface only
        """Return a valid access token, refreshing as needed."""


@dataclass
class AccessToken:
    value: str
    expires_at: datetime


DEFAULT_EXPIRY_LEEWAY = 60


class OAuthTokenProvider:
    def __init__(
        self,
        *,
        token_url: str,
        client_id: str,
        client_secret: str,
        scope: str,
        session: Optional[Session],
        timeout: float,
        now_fn: Optional[Callable[[], datetime]] = None,
        expiry_leeway: int = DEFAULT_EXPIRY_LEEWAY,
    ) -> None:
        self._token_url = token_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._scope = scope
        self._session = session or requests.Session()
        self._timeout = timeout
        self._now_fn = now_fn or (lambda: datetime.now(timezone.utc))
        self._expiry_leeway = expiry_leeway
        self._cached_token: Optional[AccessToken] = None

    def get_access_token(self) -> str:
        now = self._now()

        if self._cached_token and now < self._cached_token.expires_at:
            return self._cached_token.value

        self._cached_token = self._request_token(now)
        return self._cached_token.value

    def _request_token(self, request_time: datetime) -> AccessToken:
        payload = {
            "grant_type": "client_credentials",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "scope": self._scope,
        }
        response = self._session.post(
            self._token_url,
            data=payload,
            timeout=self._timeout,
        )

        if response.status_code != 200:
            raise RuntimeError(
                f"Token request failed with status {response.status_code}: {response.text}"
            )

        data = self._parse_response(response)

        access_token = data.get("access_token")
        expires_in = data.get("expires_in")

        if not isinstance(access_token, str) or not access_token:
            raise RuntimeError("Token response missing access_token")

        if not isinstance(expires_in, (int, float)):
            raise RuntimeError("Token response missing expires_in")

        lifetime = max(int(expires_in) - self._expiry_leeway, 1)
        expires_at = request_time + timedelta(seconds=lifetime)

        return AccessToken(value=access_token, expires_at=expires_at)

    def _parse_response(self, response: Response) -> dict:
        try:
            return response.json()
        except ValueError as exc:
            raise RuntimeError("Failed to decode token response as JSON") from exc

    def _now(self) -> datetime:
        ts = self._now_fn()
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts
