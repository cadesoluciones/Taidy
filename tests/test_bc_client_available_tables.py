# -*- coding: utf-8 -*-
"""
BusinessCentralClient.list_available_tables() -- confirmed live against the
real BC sandbox that a plain GET on the OData v4 service root (no
Company(...) segment) returns every entity set, including every
"APIxxxxx"-style custom page already used in tables.yaml under its exact
existing id (18/19 of the real, currently-configured URLs matched
byte-for-byte after restoring the {ENVIRONMENT} placeholder). Doesn't cover
the couple of tables that instead use BC's newer "Custom APIs" mechanism
(.../api/{publisher}/{group}/v{version}/...) -- a separate service root
with no equivalent "list everything" endpoint.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import src.bc_client.api as bc_api_module  # noqa: E402
from src.bc_client.api import BusinessCentralClient, BusinessCentralError  # noqa: E402
from src.bc_client.config import Settings, TableConfig  # noqa: E402


class _FakeResponse:
    def __init__(self, status_code, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text

    def json(self):
        return self._json_data


class _FakeSession:
    def __init__(self, response):
        self._response = response
        self.requests = []

    def get(self, url, **kwargs):
        self.requests.append(url)
        return self._response


class _FakeTokenProvider:
    def get_access_token(self):
        return "fake-token"


def _settings(tables) -> Settings:
    return Settings(
        tenant_id="t",
        client_id="c",
        client_secret="s",
        scope="scope",
        token_url="https://login.microsoftonline.com/t/oauth2/v2.0/token",
        company_id=None,
        company_name="CADE Soluciones",
        tables=tables,
        page_size=1000,
        output_dir=Path("."),
    )


def _client(settings, session):
    return BusinessCentralClient(settings=settings, token_provider=_FakeTokenProvider(), session=session)


_EXISTING_TABLE_URL = (
    "https://api.businesscentral.dynamics.com/v2.0/tenant-guid/SANDBOX_CADE/ODataV4/"
    "Company('CADE%20Soluciones')/APIexisting"
)


def test_list_available_tables_returns_full_ready_to_save_urls(monkeypatch):
    monkeypatch.setattr(bc_api_module, "resolve_environment", lambda: "SANDBOX_CADE")
    settings = _settings([TableConfig(name="bc_existing", url=_EXISTING_TABLE_URL)])
    session = _FakeSession(
        _FakeResponse(
            200,
            {"value": [{"name": "Company", "kind": "EntitySet"}, {"name": "APIabc", "kind": "EntitySet"}]},
        )
    )
    client = _client(settings, session)

    tables = client.list_available_tables()

    assert tables == [
        {
            "name": "https://api.businesscentral.dynamics.com/v2.0/tenant-guid/{ENVIRONMENT}/ODataV4/"
            "Company('CADE%20Soluciones')/APIabc",
            "label": "APIabc",
        },
        {
            "name": "https://api.businesscentral.dynamics.com/v2.0/tenant-guid/{ENVIRONMENT}/ODataV4/"
            "Company('CADE%20Soluciones')/Company",
            "label": "Company",
        },
    ]
    # Queried the service root (no Company(...) segment), not a specific table.
    assert session.requests == [
        "https://api.businesscentral.dynamics.com/v2.0/tenant-guid/SANDBOX_CADE/ODataV4/"
    ]


def test_list_available_tables_encodes_a_company_name_with_a_quote(monkeypatch):
    monkeypatch.setattr(bc_api_module, "resolve_environment", lambda: "SANDBOX_CADE")
    settings = _settings([TableConfig(name="bc_existing", url=_EXISTING_TABLE_URL)])
    settings.company_name = "O'Reilly & Co"
    session = _FakeSession(_FakeResponse(200, {"value": [{"name": "APIabc", "kind": "EntitySet"}]}))
    client = _client(settings, session)

    tables = client.list_available_tables()

    assert "Company('O%27%27Reilly%20%26%20Co')/APIabc" in tables[0]["name"]


def test_list_available_tables_raises_when_no_tables_are_configured():
    settings = _settings([])
    client = _client(settings, _FakeSession(_FakeResponse(200, {"value": []})))

    with pytest.raises(BusinessCentralError, match="No hay ninguna tabla"):
        client.list_available_tables()


def test_list_available_tables_raises_on_an_unexpected_url_shape():
    settings = _settings([TableConfig(name="bc_odd", url="https://example.com/not-odata/x")])
    client = _client(settings, _FakeSession(_FakeResponse(200, {"value": []})))

    with pytest.raises(BusinessCentralError, match="ODataV4"):
        client.list_available_tables()


def test_list_available_tables_skips_malformed_entries(monkeypatch):
    monkeypatch.setattr(bc_api_module, "resolve_environment", lambda: "SANDBOX_CADE")
    settings = _settings([TableConfig(name="bc_existing", url=_EXISTING_TABLE_URL)])
    session = _FakeSession(
        _FakeResponse(200, {"value": [{"kind": "EntitySet"}, {"name": ""}, {"name": "APIok"}, "not-a-dict"]})
    )
    client = _client(settings, session)

    tables = client.list_available_tables()

    assert [t["label"] for t in tables] == ["APIok"]
