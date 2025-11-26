from pathlib import Path
import pytest
import responses

from src.bc_client.api import BusinessCentralClient
from src.bc_client.auth import TokenProvider
from src.bc_client.config import Settings, TableConfig


class StubTokenProvider(TokenProvider):
    def __init__(self, value: str) -> None:
        self._value = value

    def get_access_token(self) -> str:
        return self._value


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


def _client(token: str = "token") -> BusinessCentralClient:
    return BusinessCentralClient(
        settings=_settings(),
        token_provider=StubTokenProvider(token),
        session=None,
        timeout=5,
    )


@responses.activate
def test_get_table_rows_single_page() -> None:
    settings = _settings()
    table = settings.tables[0]
    # Return a single JSON payload so pagination stays in the single-page path.
    responses.add(
        responses.GET,
        table.url,
        json={"value": [{"id": 1}, {"id": 2}]},
        status=200,
    )

    client = _client()
    rows = client.get_table_rows(table.url)

    assert rows == [{"id": 1}, {"id": 2}]
    assert len(responses.calls) == 1
    # The client should always attach the cached bearer token.
    assert responses.calls[0].request.headers["Authorization"] == "Bearer token"


@responses.activate
def test_get_table_rows_paginates() -> None:
    settings = _settings()
    table = settings.tables[0]
    next_url = "https://api.businesscentral.dynamics.com/v2.0/tenant/Sandbox/api/data/companies({})/customers?$skiptoken=abc".format(
        settings.company_id
    )

    # Provide a nextLink so the client is forced to request a second page.
    responses.add(
        responses.GET,
        table.url,
        json={
            "value": [{"id": 1}],
            "@odata.nextLink": next_url,
        },
        status=200,
    )
    responses.add(
        responses.GET,
        next_url,
        json={"value": [{"id": 2}]},
        status=200,
    )

    client = _client()
    rows = client.get_table_rows(table.url)

    assert rows == [{"id": 1}, {"id": 2}]
    assert len(responses.calls) == 2


@responses.activate
def test_get_table_rows_raises_on_error() -> None:
    settings = _settings()
    table = settings.tables[0]
    # Error payload simulates a server-side failure condition.
    responses.add(
        responses.GET,
        table.url,
        json={"error": {"code": "Bad"}},
        status=500,
    )

    client = _client()

    with pytest.raises(RuntimeError):
        client.get_table_rows(table.url)


@responses.activate
def test_get_table_rows_sets_prefer_header_for_page_size() -> None:
    settings = _settings()
    table = settings.tables[0]
    # Ensure the Prefer header encodes the configured page size.
    responses.add(
        responses.GET,
        table.url,
        json={"value": []},
        status=200,
    )

    client = _client()
    client.get_table_rows(table.url)

    headers = responses.calls[0].request.headers
    assert headers["Prefer"] == f"odata.maxpagesize={settings.page_size}"
