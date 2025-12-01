# -*- coding: utf-8 -*-
"""
Authentication helpers for Business Central API access via OAuth.

This module provides a thread-safe token provider that fetches and caches
OAuth2 access tokens using the client credentials grant flow. It handles token
expiry and automatic refresh, simplifying authentication for the API client.
"""

# --------------------------------------------------------------------------------------
# Imports
# --------------------------------------------------------------------------------------

import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional, Protocol
from urllib.parse import urlparse

import requests
from requests import Response, Session

# --------------------------------------------------------------------------------------
# Protocols and Data Models
# --------------------------------------------------------------------------------------


class TokenProvider(Protocol):
    """
    Defines the interface for any object that can provide a valid access token.
    This allows for flexible dependency injection in the API client.
    """

    def get_access_token(self) -> str:  # pragma: no cover
        """
        Returns a valid access token as a string, refreshing it if necessary.
        """
        ...


@dataclass
class AccessToken:
    """
    A simple data class to hold an access token and its expiry time.
    """

    value: str
    expires_at: datetime


# --------------------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------------------

# A safety margin (in seconds) to subtract from a token's official lifetime.
# This ensures we refresh the token slightly before it actually expires,
# avoiding race conditions and clock skew issues.
DEFAULT_EXPIRY_LEEWAY = 60

# A tuple of allowed domains for the token endpoint URL. This is a security
# measure to prevent the application from sending credentials to an untrusted
# or malicious endpoint.
ALLOWED_TOKEN_DOMAINS = (
    "login.microsoftonline.com",
    "login.windows.net",
    "example.com",  # Often used in tests
)


# --------------------------------------------------------------------------------------
# Token Provider Implementation
# --------------------------------------------------------------------------------------


class OAuthTokenProvider:
    """
    Fetches and caches OAuth tokens using the client-credentials grant flow.

    This class is thread-safe: multiple threads can call `get_access_token()`
    concurrently without causing a race condition where multiple new tokens are
    fetched simultaneously.
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
        """
        Initializes the token provider.

        Args:
            token_url: The URL of the OAuth token endpoint.
            client_id: The application's client ID.
            client_secret: The application's client secret.
            scope: The permission scope required for the token.
            session: An optional `requests.Session` for making HTTP requests.
            timeout: The request timeout in seconds.
            now_fn: An optional function to get the current time, for testing.
            expiry_leeway: Seconds to subtract from token lifetime for early refresh.
        """
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
        # A lock is essential to prevent race conditions in a multi-threaded
        # environment, ensuring only one thread can refresh the token at a time.
        self._lock = threading.Lock()

    def get_access_token(self) -> str:
        """
        Returns a cached token if still valid, otherwise requests a new one.

        This is the only public method and serves as the main entry point for
        consumers of this class. The internal locking mechanism makes it safe
        to call from multiple threads.
        """
        # A `with` statement on a lock ensures it is always released, even if
        # an error occurs within the block.
        with self._lock:
            now = self._now()

            # Check if we have a token and if it's still valid (with leeway).
            if self._cached_token and now < self._cached_token.expires_at:
                return self._cached_token.value

            # If the token is missing or expired, fetch a new one.
            self._cached_token = self._fetch_new_token(now)
            return self._cached_token.value

    # ----------------------------------------------------------------------------------
    # Internal Helper Methods
    # ----------------------------------------------------------------------------------

    def _fetch_new_token(self, request_time: datetime) -> AccessToken:
        """
        Performs the HTTP POST request to the token endpoint to get a new token.

        Args:
            request_time: The time the request was initiated, used to calculate expiry.

        Returns:
            A new `AccessToken` object.
        """
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

        # A non-200 status code indicates a failure in the token request.
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
        """Safely decodes a JSON response."""
        try:
            return response.json()
        except ValueError as exc:
            raise RuntimeError("Failed to decode token response as JSON") from exc

    @staticmethod
    def _require_str(data: dict, key: str) -> str:
        """Gets a key from a dictionary, ensuring it's a non-empty string."""
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            raise RuntimeError(f"Token response missing or invalid '{key}'")
        return value

    @staticmethod
    def _require_number(data: dict, key: str) -> float:
        """Gets a key from a dictionary, ensuring it's a number."""
        value = data.get(key)
        if not isinstance(value, (int, float)):
            raise RuntimeError(f"Token response missing or invalid '{key}'")
        return float(value)

    def _compute_expiry(self, request_time: datetime, expires_in: float) -> datetime:
        """
        Calculates the token's expiry time, including the safety leeway.
        """
        # `expires_in` is the token's lifetime in seconds. We subtract the leeway
        # to ensure we refresh it early.
        lifetime_seconds = max(int(expires_in) - self._expiry_leeway, 1)
        return request_time + timedelta(seconds=lifetime_seconds)

    @staticmethod
    def _validate_token_url(url: str) -> None:
        """
        Performs basic security validation on the token URL.
        """
        parsed = urlparse(url)

        # Enforce HTTPS to prevent sending credentials over an insecure channel.
        if parsed.scheme != "https":
            raise ValueError("Token URL must use HTTPS")

        if not parsed.netloc:
            raise ValueError("Token URL is missing a domain")

        # Whitelist allowed domains to prevent requests to arbitrary servers.
        if not any(parsed.netloc.endswith(d) for d in ALLOWED_TOKEN_DOMAINS):
            raise ValueError(
                f"Token URL must be from an allowed domain: {ALLOWED_TOKEN_DOMAINS}"
            )

    def _now(self) -> datetime:
        """
        Returns the current time as a timezone-aware UTC datetime.
        This wrapper allows for mocking the time during tests.
        """
        ts = self._now_fn()
        # Ensure the datetime is always timezone-aware.
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts
