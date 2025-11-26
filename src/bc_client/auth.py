"""Authentication helpers for Business Central API access."""

import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional, Protocol
from urllib.parse import urlparse

import requests
from requests import Response, Session


class TokenProvider(Protocol):
    """Anything that can return a valid access token."""

    def get_access_token(self) -> str:  # pragma: no cover
        """Return a valid access token, refreshing if needed."""


@dataclass
class AccessToken:
    value: str
    expires_at: datetime


DEFAULT_EXPIRY_LEEWAY = 60
ALLOWED_TOKEN_DOMAINS = (
    "login.microsoftonline.com",
    "login.windows.net",
    "example.com",
)


class OAuthTokenProvider:
    """
    Fetches OAuth tokens using client-credentials and caches them until expiry.

    Thread-safe: multiple threads can call get_access_token() without racing.
    """

    def __init__(
        self,
        *,
        token_url: str,
        client_id: str,
        client_secret: str,
        scope: str,
        session: Optional[Session] = None,
        timeout: float = 30.0,
        now_fn: Optional[Callable[[], datetime]] = None,
        expiry_leeway: int = DEFAULT_EXPIRY_LEEWAY,
    ) -> None:
        self._validate_token_url(token_url)

        self._token_url = token_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._scope = scope

        self._session = session or requests.Session()
        self._timeout = timeout

        self._now_fn = now_fn or (lambda: datetime.now(timezone.utc))
        self._expiry_leeway = expiry_leeway

        self._cached_token: Optional[AccessToken] = None
        self._lock = threading.Lock()

    def get_access_token(self) -> str:
        """
        Return a cached token if still valid, otherwise request a new one.
        """
        with self._lock:
            now = self._now()

            if self._cached_token and now < self._cached_token.expires_at:
                return self._cached_token.value

            self._cached_token = self._fetch_new_token(now)
            return self._cached_token.value

    # -------------------------
    # Internal helpers
    # -------------------------

    def _fetch_new_token(self, request_time: datetime) -> AccessToken:
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
                f"Token request failed ({response.status_code}): {response.text}"
            )

        data = self._read_json(response)
        token_value = self._require_str(data, "access_token")
        expires_in = self._require_number(data, "expires_in")

        expires_at = self._compute_expiry(request_time, expires_in)
        return AccessToken(value=token_value, expires_at=expires_at)

    @staticmethod
    def _read_json(response: Response) -> dict:
        try:
            return response.json()
        except ValueError as exc:
            raise RuntimeError("Failed to decode token response as JSON") from exc

    @staticmethod
    def _require_str(data: dict, key: str) -> str:
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            raise RuntimeError(f"Token response missing or invalid '{key}'")
        return value

    @staticmethod
    def _require_number(data: dict, key: str) -> float:
        value = data.get(key)
        if not isinstance(value, (int, float)):
            raise RuntimeError(f"Token response missing or invalid '{key}'")
        return float(value)

    def _compute_expiry(self, request_time: datetime, expires_in: float) -> datetime:
        # Subtract a small leeway so we refresh slightly before real expiry.
        lifetime_seconds = max(int(expires_in) - self._expiry_leeway, 1)
        return request_time + timedelta(seconds=lifetime_seconds)

    @staticmethod
    def _validate_token_url(url: str) -> None:
        parsed = urlparse(url)

        if parsed.scheme != "https":
            raise ValueError("Token URL must use HTTPS")

        if not parsed.netloc:
            raise ValueError("Token URL is missing a domain")

        if not any(parsed.netloc.endswith(d) for d in ALLOWED_TOKEN_DOMAINS):
            raise ValueError(
                f"Token URL must be from allowed domains: {ALLOWED_TOKEN_DOMAINS}"
            )

    def _now(self) -> datetime:
        ts = self._now_fn()
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts
