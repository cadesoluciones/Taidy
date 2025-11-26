"""Unit tests for API client basic functionality."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.bc_client.api import BusinessCentralClient, BusinessCentralError
from src.bc_client.config import Settings, TableConfig


def _settings() -> Settings:
    return Settings(
        tenant_id="tenant",
        environment="Sandbox",
        client_id="client",
        client_secret="secret",
        scope="scope",
        token_url="https://example.com/token",
        company_id="00000000-0000-0000-0000-000000000000",
        company_name="Company",
        tables=[
            TableConfig(
                name="customers",
                url="https://api.businesscentral.dynamics.com/v2.0/tenant/Sandbox/api/data/companies(00000000-0000-0000-0000-000000000000)/customers",
            )
        ],
        page_size=2,
        output_dir=Path("/tmp"),
    )


def _token_provider(token: str = "token") -> SimpleNamespace:
    def get_access_token() -> str:
        return token

    return SimpleNamespace(get_access_token=get_access_token)


def _response(status_code: int, text: str = "") -> SimpleNamespace:
    return SimpleNamespace(status_code=status_code, text=text)


def _session(response: SimpleNamespace) -> SimpleNamespace:
    # Capture request metadata so tests can assert on headers after the call.
    calls: list[tuple[str, dict[str, object]]] = []

    def get(url: str, **kwargs):
        calls.append((url, kwargs))
        return response

    return SimpleNamespace(get=get, calls=calls)


def _client(
    *,
    token: str = "token",
    session: SimpleNamespace | None = None,
) -> BusinessCentralClient:
    return BusinessCentralClient(
        settings=_settings(),
        token_provider=_token_provider(token),
        session=session,
        timeout=5,
    )


def test_get_adds_authorization_header() -> None:
    """_get should add Bearer token to request headers."""
    session = _session(_response(status_code=200))
    client = _client(token="test_token", session=session)

    client._get("https://example.com/test")

    _, call_kwargs = session.calls[0]
    assert call_kwargs["headers"]["Authorization"] == "Bearer test_token"


@pytest.mark.parametrize(
    "status_code",
    [404, 500],
)
def test_get_raises_on_error(status_code: int) -> None:
    """Any 4xx/5xx result should surface as a BusinessCentralError."""
    session = _session(_response(status_code=status_code, text="boom"))
    client = _client(session=session)

    with pytest.raises(BusinessCentralError, match=str(status_code)):
        client._get("https://example.com/test")
