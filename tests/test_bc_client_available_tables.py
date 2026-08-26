# -*- coding: utf-8 -*-
"""
BusinessCentralClient.list_available_odata_tables() /
list_available_custom_api_tables() -- confirmed live against the real BC
sandbox that BOTH mechanisms this project's tables use are discoverable,
each via its own root's plain GET:

1. The OData v4 service root (.../ODataV4/, no Company(...) segment)
   returns every entity set, including every "APIxxxxx"-style custom page
   already used in tables.yaml under its exact existing id.
2. Each BC "Custom APIs" group (.../api/{publisher}/{group}/{version}/)
   responds to a plain GET on ITS OWN root with a full service document --
   e.g. .../api/cade/Proyecto/v1.0/ listed 21 entities live, only one of
   which ("recursos") was already tracked in tables.yaml. There's no single
   endpoint listing every group across the whole tenant, so only groups
   already used by at least one currently-configured table get queried.

Combined against the real sandbox: 20/21 of the real, currently-configured
URLs matched byte-for-byte after restoring the {ENVIRONMENT} placeholder
(the one mismatch was already a differently-encoded quirk in tables.yaml
itself, unrelated to this code). Split into two independent methods (and
two admin UI buttons) rather than one merged list/button, per explicit
request -- OData and Custom APIs are different enough mechanisms that
mixing their results made the picker harder to scan.
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


@pytest.fixture(autouse=True)
def _no_known_extra_groups(monkeypatch):
    """Every other test in this file focuses on auto-discovery or an
    explicit `extra_group` and doesn't mock a response for the
    always-probed `_KNOWN_UNDISCOVERABLE_GROUPS` roots -- clear that list
    here so they keep exercising exactly what they say. A dedicated test
    below restores it to verify the real behavior."""
    monkeypatch.setattr(bc_api_module, "_KNOWN_UNDISCOVERABLE_GROUPS", ())


_PREFIX = "https://api.businesscentral.dynamics.com/v2.0/tenant-guid/SANDBOX_CADE"
_ODATA_ROOT = f"{_PREFIX}/ODataV4/"
_EXISTING_TABLE_URL = f"{_ODATA_ROOT}Company('CADE%20Soluciones')/APIexisting"
_PROYECTO_GROUP_ROOT = f"{_PREFIX}/api/cade/Proyecto/v1.0/"
_PROYECTO_TABLE_URL = f"{_PROYECTO_GROUP_ROOT}recursos?company=CADE%20Soluciones"

# The two roots above are what actually gets requested (real, resolved
# environment) -- but a returned "label" carries the {ENVIRONMENT}
# placeholder instead, ready to save into tables.yaml unchanged.
_ODATA_ROOT_SAVED = _ODATA_ROOT.replace("SANDBOX_CADE", "{ENVIRONMENT}")
_PROYECTO_GROUP_ROOT_SAVED = _PROYECTO_GROUP_ROOT.replace("SANDBOX_CADE", "{ENVIRONMENT}")


# --------------------------------------------------------------------------------------
# list_available_odata_tables()
# --------------------------------------------------------------------------------------


def test_list_available_odata_tables_returns_full_ready_to_save_urls(monkeypatch):
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

    tables = client.list_available_odata_tables()

    assert tables == [
        {"name": "APIabc", "label": f"{_ODATA_ROOT_SAVED}Company('CADE%20Soluciones')/APIabc"},
        {"name": "Company", "label": f"{_ODATA_ROOT_SAVED}Company('CADE%20Soluciones')/Company"},
    ]
    # Queried the service root (no Company(...) segment), not a specific table.
    assert session.requests == [_ODATA_ROOT]


def test_list_available_odata_tables_encodes_a_company_name_with_a_quote(monkeypatch):
    monkeypatch.setattr(bc_api_module, "resolve_environment", lambda: "SANDBOX_CADE")
    settings = _settings([TableConfig(name="bc_existing", url=_EXISTING_TABLE_URL)])
    settings.company_name = "O'Reilly & Co"
    session = _FakeSession({_ODATA_ROOT: _FakeResponse(200, {"value": [{"name": "APIabc", "kind": "EntitySet"}]})})
    client = _client(settings, session)

    tables = client.list_available_odata_tables()

    assert "Company('O%27%27Reilly%20%26%20Co')/APIabc" in tables[0]["label"]


def test_list_available_odata_tables_raises_when_no_odata_table_is_configured():
    settings = _settings([TableConfig(name="bc_custom_api_only", url=_PROYECTO_TABLE_URL)])
    client = _client(settings, _FakeSession({}))

    with pytest.raises(BusinessCentralError, match="Ninguna tabla configurada usa el API OData"):
        client.list_available_odata_tables()


def test_list_available_odata_tables_skips_malformed_entries(monkeypatch):
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

    tables = client.list_available_odata_tables()

    assert [t["name"] for t in tables] == ["APIok"]


# --------------------------------------------------------------------------------------
# list_available_custom_api_tables()
# --------------------------------------------------------------------------------------


def test_list_available_custom_api_tables_merges_in_a_group(monkeypatch):
    monkeypatch.setattr(bc_api_module, "resolve_environment", lambda: "SANDBOX_CADE")
    settings = _settings([TableConfig(name="bc_recursos", url=_PROYECTO_TABLE_URL)])
    session = _FakeSession(
        {_PROYECTO_GROUP_ROOT: _FakeResponse(200, {"value": [{"name": "recursos"}, {"name": "jobPlanningLines"}]})}
    )
    client = _client(settings, session)

    tables = client.list_available_custom_api_tables()

    assert tables == [
        {
            "name": "Proyecto/jobPlanningLines",
            "label": f"{_PROYECTO_GROUP_ROOT_SAVED}jobPlanningLines?company=CADE%20Soluciones",
        },
        {"name": "Proyecto/recursos", "label": f"{_PROYECTO_GROUP_ROOT_SAVED}recursos?company=CADE%20Soluciones"},
    ]
    assert session.requests == [_PROYECTO_GROUP_ROOT]


def test_list_available_custom_api_tables_queries_each_distinct_group_only_once(monkeypatch):
    monkeypatch.setattr(bc_api_module, "resolve_environment", lambda: "SANDBOX_CADE")
    settings = _settings(
        [
            TableConfig(name="bc_recursos", url=_PROYECTO_TABLE_URL),
            TableConfig(name="bc_hitos", url=f"{_PROYECTO_GROUP_ROOT}proyectoHitosAPI?company=CADE%20Soluciones"),
        ]
    )
    session = _FakeSession({_PROYECTO_GROUP_ROOT: _FakeResponse(200, {"value": [{"name": "recursos"}]})})
    client = _client(settings, session)

    client.list_available_custom_api_tables()

    assert session.requests == [_PROYECTO_GROUP_ROOT]


def test_list_available_custom_api_tables_ignores_odata_style_urls(monkeypatch):
    """Only /api/ URLs contribute a group to query -- an ODataV4-style
    table shouldn't make this method try to treat "ODataV4" as a
    publisher/group/version triple."""
    settings = _settings([TableConfig(name="bc_existing", url=_EXISTING_TABLE_URL)])
    client = _client(settings, _FakeSession({}))

    with pytest.raises(BusinessCentralError, match="No se encontraron tablas"):
        client.list_available_custom_api_tables()


def test_list_available_custom_api_tables_raises_when_the_only_group_fails(monkeypatch):
    monkeypatch.setattr(bc_api_module, "resolve_environment", lambda: "SANDBOX_CADE")
    settings = _settings([TableConfig(name="bc_recursos", url=_PROYECTO_TABLE_URL)])
    session = _FakeSession({_PROYECTO_GROUP_ROOT: _FakeResponse(404, text="Not Found")})
    client = _client(settings, session)

    with pytest.raises(BusinessCentralError, match="No se encontraron tablas"):
        client.list_available_custom_api_tables()


def test_list_available_custom_api_tables_extra_group_is_included_even_with_no_matching_table(monkeypatch):
    """The real bug reported live: a BC page can declare APIGroup
    "Contabilidad"/"Compras" while every table actually configured for it
    still points at the plain OData id instead -- so auto-discovery (which
    only looks at existing /api/ URLs) never finds those groups on its
    own. `extra_group` probes one explicitly, regardless of what's
    configured."""
    monkeypatch.setattr(bc_api_module, "resolve_environment", lambda: "SANDBOX_CADE")
    contabilidad_root = f"{_PREFIX}/api/cade/Contabilidad/v1.0/"
    # Only an ODataV4-style table configured -- nothing to auto-discover
    # any Custom APIs group from.
    settings = _settings([TableConfig(name="bc_existing", url=_EXISTING_TABLE_URL)])
    session = _FakeSession({contabilidad_root: _FakeResponse(200, {"value": [{"name": "GLAccount"}]})})
    client = _client(settings, session)

    tables = client.list_available_custom_api_tables(extra_group=("cade", "Contabilidad", "v1.0"))

    assert tables == [
        {
            "name": "Contabilidad/GLAccount",
            "label": f"{contabilidad_root.replace('SANDBOX_CADE', '{ENVIRONMENT}')}GLAccount?company=CADE%20Soluciones",
        }
    ]
    assert session.requests == [contabilidad_root]


def test_list_available_custom_api_tables_extra_group_merges_with_auto_discovered_ones(monkeypatch):
    monkeypatch.setattr(bc_api_module, "resolve_environment", lambda: "SANDBOX_CADE")
    contabilidad_root = f"{_PREFIX}/api/cade/Contabilidad/v1.0/"
    settings = _settings([TableConfig(name="bc_recursos", url=_PROYECTO_TABLE_URL)])
    session = _FakeSession(
        {
            _PROYECTO_GROUP_ROOT: _FakeResponse(200, {"value": [{"name": "recursos"}]}),
            contabilidad_root: _FakeResponse(200, {"value": [{"name": "GLAccount"}]}),
        }
    )
    client = _client(settings, session)

    tables = client.list_available_custom_api_tables(extra_group=("cade", "Contabilidad", "v1.0"))

    assert {t["name"] for t in tables} == {"Proyecto/recursos", "Contabilidad/GLAccount"}
    assert sorted(session.requests) == sorted([_PROYECTO_GROUP_ROOT, contabilidad_root])


def test_list_available_custom_api_tables_extra_group_already_seen_is_not_queried_twice(monkeypatch):
    monkeypatch.setattr(bc_api_module, "resolve_environment", lambda: "SANDBOX_CADE")
    settings = _settings([TableConfig(name="bc_recursos", url=_PROYECTO_TABLE_URL)])
    session = _FakeSession({_PROYECTO_GROUP_ROOT: _FakeResponse(200, {"value": [{"name": "recursos"}]})})
    client = _client(settings, session)

    client.list_available_custom_api_tables(extra_group=("cade", "Proyecto", "v1.0"))

    assert session.requests == [_PROYECTO_GROUP_ROOT]


def test_list_available_custom_api_tables_always_includes_known_undiscoverable_groups(monkeypatch):
    """The actual fix for the reported bug: Compras/Contabilidad must show
    up with no manual input at all, not just when the admin remembers to
    type them into the "extra group" field."""
    monkeypatch.setattr(bc_api_module, "resolve_environment", lambda: "SANDBOX_CADE")
    contabilidad_root = f"{_PREFIX}/api/cade/Contabilidad/v1.0/"
    monkeypatch.setattr(bc_api_module, "_KNOWN_UNDISCOVERABLE_GROUPS", (("cade", "Contabilidad", "v1.0"),))
    # Only an ODataV4-style table configured -- nothing to auto-discover
    # any Custom APIs group from, and no extra_group passed in either.
    settings = _settings([TableConfig(name="bc_existing", url=_EXISTING_TABLE_URL)])
    session = _FakeSession({contabilidad_root: _FakeResponse(200, {"value": [{"name": "GLAccount"}]})})
    client = _client(settings, session)

    tables = client.list_available_custom_api_tables()

    assert tables == [
        {
            "name": "Contabilidad/GLAccount",
            "label": f"{contabilidad_root.replace('SANDBOX_CADE', '{ENVIRONMENT}')}GLAccount?company=CADE%20Soluciones",
        }
    ]
    assert session.requests == [contabilidad_root]


def test_list_available_custom_api_tables_known_group_merges_with_auto_discovered_and_extra(monkeypatch):
    monkeypatch.setattr(bc_api_module, "resolve_environment", lambda: "SANDBOX_CADE")
    contabilidad_root = f"{_PREFIX}/api/cade/Contabilidad/v1.0/"
    compras_root = f"{_PREFIX}/api/cade/Compras/v1.0/"
    monkeypatch.setattr(bc_api_module, "_KNOWN_UNDISCOVERABLE_GROUPS", (("cade", "Contabilidad", "v1.0"),))
    settings = _settings([TableConfig(name="bc_recursos", url=_PROYECTO_TABLE_URL)])
    session = _FakeSession(
        {
            _PROYECTO_GROUP_ROOT: _FakeResponse(200, {"value": [{"name": "recursos"}]}),
            contabilidad_root: _FakeResponse(200, {"value": [{"name": "GLAccount"}]}),
            compras_root: _FakeResponse(200, {"value": [{"name": "vendors"}]}),
        }
    )
    client = _client(settings, session)

    tables = client.list_available_custom_api_tables(extra_group=("cade", "Compras", "v1.0"))

    assert {t["name"] for t in tables} == {"Proyecto/recursos", "Contabilidad/GLAccount", "Compras/vendors"}


def test_list_available_custom_api_tables_known_group_already_auto_discovered_is_not_queried_twice(monkeypatch):
    monkeypatch.setattr(bc_api_module, "resolve_environment", lambda: "SANDBOX_CADE")
    monkeypatch.setattr(bc_api_module, "_KNOWN_UNDISCOVERABLE_GROUPS", (("cade", "Proyecto", "v1.0"),))
    settings = _settings([TableConfig(name="bc_recursos", url=_PROYECTO_TABLE_URL)])
    session = _FakeSession({_PROYECTO_GROUP_ROOT: _FakeResponse(200, {"value": [{"name": "recursos"}]})})
    client = _client(settings, session)

    client.list_available_custom_api_tables()

    assert session.requests == [_PROYECTO_GROUP_ROOT]


def test_list_available_custom_api_tables_known_group_that_fails_does_not_hide_the_rest(monkeypatch):
    monkeypatch.setattr(bc_api_module, "resolve_environment", lambda: "SANDBOX_CADE")
    monkeypatch.setattr(bc_api_module, "_KNOWN_UNDISCOVERABLE_GROUPS", (("cade", "Contabilidad", "v1.0"),))
    contabilidad_root = f"{_PREFIX}/api/cade/Contabilidad/v1.0/"
    settings = _settings([TableConfig(name="bc_recursos", url=_PROYECTO_TABLE_URL)])
    session = _FakeSession(
        {
            _PROYECTO_GROUP_ROOT: _FakeResponse(200, {"value": [{"name": "recursos"}]}),
            contabilidad_root: _FakeResponse(404, text="Not Found"),
        }
    )
    client = _client(settings, session)

    tables = client.list_available_custom_api_tables()

    assert [t["name"] for t in tables] == ["Proyecto/recursos"]


def test_list_available_custom_api_tables_skips_a_failing_group_without_failing_the_rest(monkeypatch):
    """Non-fatal per-group: one Custom APIs group this service principal
    can no longer reach shouldn't hide entities from a different group
    that still works."""
    monkeypatch.setattr(bc_api_module, "resolve_environment", lambda: "SANDBOX_CADE")
    other_group_root = f"{_PREFIX}/api/cade/CRM/v1.0/"
    settings = _settings(
        [
            TableConfig(name="bc_recursos", url=_PROYECTO_TABLE_URL),
            TableConfig(name="bc_contact", url=f"{other_group_root}contacts?company=CADE%20Soluciones"),
        ]
    )
    session = _FakeSession(
        {
            _PROYECTO_GROUP_ROOT: _FakeResponse(404, text="Not Found"),
            other_group_root: _FakeResponse(200, {"value": [{"name": "contacts"}]}),
        }
    )
    client = _client(settings, session)

    tables = client.list_available_custom_api_tables()

    assert [t["name"] for t in tables] == ["CRM/contacts"]
