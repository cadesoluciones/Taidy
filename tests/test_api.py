from __future__ import annotations

from pathlib import Path
from urllib.parse import urlencode

import pytest
import responses

from bc_client.api import BusinessCentralClient
from bc_client.auth import TokenProvider
from bc_client.config import Settings, TableConfig


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
        tables=[TableConfig(name="customers", url="https://api.businesscentral.dynamics.com/v2.0/tenant/Sandbox/api/data/companies(00000000-0000-0000-0000-000000000000)/customers")],
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


def _initial_url(settings: Settings, table: str) -> str:
    params = urlencode({"$top": settings.page_size})
    return f"{table}?{params}"


@responses.activate
def test_iter_table_rows_single_page() -> None:
    settings = _settings()
    table = settings.tables[0]
    initial_url = _initial_url(settings, table.url)
    responses.add(
        responses.GET,
        initial_url,
        json={"value": [{"id": 1}, {"id": 2}]},
        status=200,
    )

    client = _client()
    rows = list(client.iter_table_rows(table.url))

    assert rows == [{"id": 1}, {"id": 2}]
    assert len(responses.calls) == 1
    assert responses.calls[0].request.headers["Authorization"] == "Bearer token"


@responses.activate
def test_iter_table_rows_paginates() -> None:
    settings = _settings()
    table = settings.tables[0]
    initial_url = _initial_url(settings, table.url)
    next_url = "https://api.businesscentral.dynamics.com/v2.0/tenant/Sandbox/api/data/companies({})/customers?$skiptoken=abc".format(
        settings.company_id
    )

    responses.add(
        responses.GET,
        initial_url,
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
    rows = list(client.iter_table_rows(table.url))

    assert rows == [{"id": 1}, {"id": 2}]
    assert len(responses.calls) == 2


@responses.activate
def test_iter_table_rows_raises_on_error() -> None:
    settings = _settings()
    table = settings.tables[0]
    initial_url = _initial_url(settings, table.url)
    responses.add(
        responses.GET,
        initial_url,
        json={"error": {"code": "Bad"}},
        status=500,
    )

    client = _client()

    with pytest.raises(RuntimeError):
        list(client.iter_table_rows(table.url))
