# -*- coding: utf-8 -*-
"""
BusinessCentralClient.list_available_tables() -- confirmed live against the
real BC sandbox that BOTH mechanisms this project's tables use are
discoverable:

1. A plain GET on the OData v4 service root (no Company(...) segment)
   returns every entity set, including every "APIxxxxx"-style custom page
   already used in tables.yaml under its exact existing id.
2. Each BC "Custom APIs" group (.../api/{publisher}/{group}/{version}/) also
   responds to a plain GET on ITS OWN root with a full service document --
   e.g. .../api/cade/Proyecto/v1.0/ listed 21 entities live, only one of
   which ("recursos") was already tracked in tables.yaml. There's no single
   endpoint listing every group across the whole tenant, so only groups
   already used by at least one currently-configured table get queried.

Combined against the real sandbox: 20/21 of the real, currently-configured
URLs matched byte-for-byte after restoring the {ENVIRONMENT} placeholder
(the one mismatch was already a differently-encoded quirk in tables.yaml
itself, unrelated to this code).
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
    """Keyed by exact URL -- a request for a URL with no matching response
    fails loudly (KeyError) rather than silently reusing an unrelated one,
    since these tests care about exactly which roots get queried."""

    def __init__(self, responses_by_url):
        self._responses = dict(responses_by_url)
        self.requests = []

    def get(self, url, **kwargs):
        self.requests.append(url)
        return self._responses[url]


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


_PREFIX = "https://api.businesscentral.dynamics.com/v2.0/tenant-guid/SANDBOX_CADE"
_ODATA_ROOT = f"{_PREFIX}/ODataV4/"
_EXISTING_TABLE_URL = f"{_ODATA_ROOT}Company('CADE%20Soluciones')/APIexisting"
_PROYECTO_GROUP_ROOT = f"{_PREFIX}/api/cade/Proyecto/v1.0/"
_PROYECTO_TABLE_URL = f"{_PROYECTO_GROUP_ROOT}recursos?company=CADE%20Soluciones"

# The two roots above are what actually gets requested (real, resolved
# environment) -- but a returned "name" carries the {ENVIRONMENT}
# placeholder instead, ready to save into tables.yaml unchanged.
_ODATA_ROOT_SAVED = _ODATA_ROOT.replace("SANDBOX_CADE", "{ENVIRONMENT}")
_PROYECTO_GROUP_ROOT_SAVED = _PROYECTO_GROUP_ROOT.replace("SANDBOX_CADE", "{ENVIRONMENT}")


def test_list_available_tables_returns_full_ready_to_save_urls(monkeypatch):
    monkeypatch.setattr(bc_api_module, "resolve_environment", lambda: "SANDBOX_CADE")
    settings = _settings([TableConfig(name="bc_existing", url=_EXISTING_TABLE_URL)])
    session = _FakeSession(
        {
            _ODATA_ROOT: _FakeResponse(
                200, {"value": [{"name": "Company", "kind": "EntitySet"}, {"name": "APIabc", "kind": "EntitySet"}]}
            )
        }
    )
    client = _client(settings, session)

    tables = client.list_available_tables()

    assert tables == [
        {"name": "APIabc", "label": f"{_ODATA_ROOT_SAVED}Company('CADE%20Soluciones')/APIabc"},
        {"name": "Company", "label": f"{_ODATA_ROOT_SAVED}Company('CADE%20Soluciones')/Company"},
    ]
    # Queried the service root (no Company(...) segment), not a specific table.
    assert session.requests == [_ODATA_ROOT]


def test_list_available_tables_encodes_a_company_name_with_a_quote(monkeypatch):
    monkeypatch.setattr(bc_api_module, "resolve_environment", lambda: "SANDBOX_CADE")
    settings = _settings([TableConfig(name="bc_existing", url=_EXISTING_TABLE_URL)])
    settings.company_name = "O'Reilly & Co"
    session = _FakeSession({_ODATA_ROOT: _FakeResponse(200, {"value": [{"name": "APIabc", "kind": "EntitySet"}]})})
    client = _client(settings, session)

    tables = client.list_available_tables()

    assert "Company('O%27%27Reilly%20%26%20Co')/APIabc" in tables[0]["label"]


def test_list_available_tables_raises_when_no_tables_are_configured():
    settings = _settings([])
    client = _client(settings, _FakeSession({}))

    with pytest.raises(BusinessCentralError, match="No hay ninguna tabla"):
        client.list_available_tables()


def test_list_available_tables_raises_when_nothing_is_discoverable():
    """Neither an ODataV4 nor an /api/ style URL -- there's nothing to query."""
    settings = _settings([TableConfig(name="bc_odd", url="https://example.com/not-odata/x")])
    client = _client(settings, _FakeSession({}))

    with pytest.raises(BusinessCentralError, match="No se encontraron tablas"):
        client.list_available_tables()


def test_list_available_tables_skips_malformed_odata_entries(monkeypatch):
    monkeypatch.setattr(bc_api_module, "resolve_environment", lambda: "SANDBOX_CADE")
    settings = _settings([TableConfig(name="bc_existing", url=_EXISTING_TABLE_URL)])
    session = _FakeSession(
        {
            _ODATA_ROOT: _FakeResponse(
                200, {"value": [{"kind": "EntitySet"}, {"name": ""}, {"name": "APIok"}, "not-a-dict"]}
            )
        }
    )
    client = _client(settings, session)

    tables = client.list_available_tables()

    assert [t["name"] for t in tables] == ["APIok"]


def test_list_available_tables_merges_in_a_custom_api_group(monkeypatch):
    monkeypatch.setattr(bc_api_module, "resolve_environment", lambda: "SANDBOX_CADE")
    settings = _settings(
        [
            TableConfig(name="bc_existing", url=_EXISTING_TABLE_URL),
            TableConfig(name="bc_recursos", url=_PROYECTO_TABLE_URL),
        ]
    )
    session = _FakeSession(
        {
            _ODATA_ROOT: _FakeResponse(200, {"value": [{"name": "APIexisting"}]}),
            _PROYECTO_GROUP_ROOT: _FakeResponse(
                200, {"value": [{"name": "recursos"}, {"name": "jobPlanningLines"}]}
            ),
        }
    )
    client = _client(settings, session)

    tables = client.list_available_tables()

    assert {
        "name": "Proyecto/recursos",
        "label": f"{_PROYECTO_GROUP_ROOT_SAVED}recursos?company=CADE%20Soluciones",
    } in tables
    assert {
        "name": "Proyecto/jobPlanningLines",
        "label": f"{_PROYECTO_GROUP_ROOT_SAVED}jobPlanningLines?company=CADE%20Soluciones",
    } in tables
    # Both roots queried exactly once each.
    assert sorted(session.requests) == sorted([_ODATA_ROOT, _PROYECTO_GROUP_ROOT])


def test_list_available_tables_queries_each_distinct_group_only_once(monkeypatch):
    monkeypatch.setattr(bc_api_module, "resolve_environment", lambda: "SANDBOX_CADE")
    settings = _settings(
        [
            TableConfig(name="bc_recursos", url=_PROYECTO_TABLE_URL),
            TableConfig(name="bc_hitos", url=f"{_PROYECTO_GROUP_ROOT}proyectoHitosAPI?company=CADE%20Soluciones"),
        ]
    )
    session = _FakeSession({_PROYECTO_GROUP_ROOT: _FakeResponse(200, {"value": [{"name": "recursos"}]})})
    client = _client(settings, session)

    client.list_available_tables()

    assert session.requests == [_PROYECTO_GROUP_ROOT]


def test_list_available_tables_skips_a_group_that_fails_without_failing_the_rest(monkeypatch):
    """Non-fatal by design: one Custom APIs group this service principal
    can no longer reach shouldn't hide the standard OData entities."""
    monkeypatch.setattr(bc_api_module, "resolve_environment", lambda: "SANDBOX_CADE")
    settings = _settings(
        [
            TableConfig(name="bc_existing", url=_EXISTING_TABLE_URL),
            TableConfig(name="bc_recursos", url=_PROYECTO_TABLE_URL),
        ]
    )
    session = _FakeSession(
        {
            _ODATA_ROOT: _FakeResponse(200, {"value": [{"name": "APIexisting"}]}),
            _PROYECTO_GROUP_ROOT: _FakeResponse(404, text="Not Found"),
        }
    )
    client = _client(settings, session)

    tables = client.list_available_tables()

    assert [t["name"] for t in tables] == ["APIexisting"]


def test_list_available_tables_works_with_only_custom_api_tables(monkeypatch):
    """An org with no ODataV4-style table at all still gets group-based
    discovery -- the ODataV4 root query is simply skipped, not an error."""
    monkeypatch.setattr(bc_api_module, "resolve_environment", lambda: "SANDBOX_CADE")
    settings = _settings([TableConfig(name="bc_recursos", url=_PROYECTO_TABLE_URL)])
    session = _FakeSession({_PROYECTO_GROUP_ROOT: _FakeResponse(200, {"value": [{"name": "recursos"}]})})
    client = _client(settings, session)

    tables = client.list_available_tables()

    assert tables == [
        {"name": "Proyecto/recursos", "label": f"{_PROYECTO_GROUP_ROOT_SAVED}recursos?company=CADE%20Soluciones"}
    ]
    assert session.requests == [_PROYECTO_GROUP_ROOT]
