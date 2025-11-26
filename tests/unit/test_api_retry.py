"""Unit tests for API client basic functionality."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from src.bc_client.api import BusinessCentralClient, BusinessCentralError
from src.bc_client.config import Settings, TableConfig


class StubTokenProvider:
    def get_access_token(self) -> str:
        return "token"


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


def test_get_adds_authorization_header() -> None:
    """_get should add Bearer token to request headers."""
    mock_token_provider = Mock()
    mock_token_provider.get_access_token.return_value = "test_token"

    client = BusinessCentralClient(
        settings=_settings(),
        token_provider=mock_token_provider,
    )

    mock_response = Mock()
    mock_response.status_code = 200

    mock_session = Mock()
    mock_session.get.return_value = mock_response
    client._session = mock_session

    client._get("https://example.com/test")

    call_kwargs = mock_session.get.call_args[1]
    assert call_kwargs["headers"]["Authorization"] == "Bearer test_token"


def test_get_raises_on_4xx_error() -> None:
    """_get should raise BusinessCentralError on 4xx status."""
    mock_token_provider = Mock()
    mock_token_provider.get_access_token.return_value = "token"

    client = BusinessCentralClient(
        settings=_settings(),
        token_provider=mock_token_provider,
    )

    mock_response = Mock()
    mock_response.status_code = 404
    mock_response.text = "Not found"

    mock_session = Mock()
    mock_session.get.return_value = mock_response
    client._session = mock_session

    with pytest.raises(BusinessCentralError, match="404"):
        client._get("https://example.com/test")


def test_get_raises_on_5xx_error() -> None:
    """_get should raise BusinessCentralError on 5xx status."""
    mock_token_provider = Mock()
    mock_token_provider.get_access_token.return_value = "token"

    client = BusinessCentralClient(
        settings=_settings(),
        token_provider=mock_token_provider,
    )

    mock_response = Mock()
    mock_response.status_code = 500
    mock_response.text = "Internal server error"

    mock_session = Mock()
    mock_session.get.return_value = mock_response
    client._session = mock_session

    with pytest.raises(BusinessCentralError, match="500"):
        client._get("https://example.com/test")
