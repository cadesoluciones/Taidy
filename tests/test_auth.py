from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable

import pytest
import responses

from bc_client.auth import OAuthTokenProvider


def _build_provider(now_fn: Callable[[], datetime] | None = None) -> OAuthTokenProvider:
    return OAuthTokenProvider(
        token_url="https://example.com/token",
        client_id="client",
        client_secret="secret",
        scope="scope",
        session=None,
        timeout=5,
        now_fn=now_fn,
    )


@responses.activate
def test_get_access_token_fetches_and_caches() -> None:
    responses.add(
        responses.POST,
        "https://example.com/token",
        json={"access_token": "abc", "expires_in": 3600},
        status=200,
    )
    provider = _build_provider()

    first = provider.get_access_token()
    second = provider.get_access_token()

    assert first == "abc"
    assert second == "abc"
    assert len(responses.calls) == 1


@responses.activate
def test_get_access_token_refreshes_when_expired() -> None:
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)

    def now_fn() -> datetime:
        return now

    provider = _build_provider(now_fn)

    responses.add(
        responses.POST,
        "https://example.com/token",
        json={"access_token": "first", "expires_in": 1},
        status=200,
    )
    token_1 = provider.get_access_token()
    assert token_1 == "first"

    now = now + timedelta(seconds=5)
    responses.add(
        responses.POST,
        "https://example.com/token",
        json={"access_token": "second", "expires_in": 3600},
        status=200,
    )
    token_2 = provider.get_access_token()

    assert token_2 == "second"
    assert len(responses.calls) == 2


@responses.activate
def test_get_access_token_raises_on_failure() -> None:
    responses.add(
        responses.POST,
        "https://example.com/token",
        json={"error": "invalid_client"},
        status=401,
    )

    provider = _build_provider()

    with pytest.raises(RuntimeError):
        provider.get_access_token()
