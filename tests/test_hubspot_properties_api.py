# -*- coding: utf-8 -*-
"""
src/hubspot_client/api.py::list_properties -- live discovery of a CRM
object type's properties for the admin UI's "available properties" helper.
Pins the hidden/calculated filtering (on by default) and the sort order,
with a fake session -- no live calls.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.hubspot_client.api import HubspotClient  # noqa: E402
from src.hubspot_client.config import Settings  # noqa: E402


def _settings() -> Settings:
    return Settings(base_url="https://api.hubapi.com", api_key="fake-key", tables=[])


class _FakeResponse:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


class _FakeReadSession:
    def __init__(self, payload):
        self._payload = payload
        self.requests = []

    def get(self, url, headers=None, params=None, timeout=None):
        self.requests.append(url)
        return _FakeResponse(200, self._payload)


_SAMPLE_PAYLOAD = {
    "results": [
        {"name": "email", "label": "Email", "hidden": False, "calculated": False},
        {"name": "firstname", "label": "First Name", "hidden": False, "calculated": False},
        {"name": "hs_object_id", "label": "Record ID", "hidden": True, "calculated": False},
        {"name": "hs_lifecyclestage_marketingqualifiedlead_date", "label": "MQL date", "hidden": False, "calculated": True},
    ]
}


def test_list_properties_filters_hidden_and_calculated_by_default():
    client = HubspotClient(settings=_settings(), session=_FakeReadSession(_SAMPLE_PAYLOAD))

    props = client.list_properties("contacts")

    assert [p["name"] for p in props] == ["email", "firstname"]


def test_list_properties_include_hidden_returns_everything():
    client = HubspotClient(settings=_settings(), session=_FakeReadSession(_SAMPLE_PAYLOAD))

    props = client.list_properties("contacts", include_hidden=True)

    assert {p["name"] for p in props} == {
        "email",
        "firstname",
        "hs_object_id",
        "hs_lifecyclestage_marketingqualifiedlead_date",
    }


def test_list_properties_sorted_by_name():
    client = HubspotClient(settings=_settings(), session=_FakeReadSession(_SAMPLE_PAYLOAD))

    props = client.list_properties("contacts", include_hidden=True)

    assert [p["name"] for p in props] == sorted(p["name"] for p in props)


def test_list_properties_hits_the_right_url():
    session = _FakeReadSession(_SAMPLE_PAYLOAD)
    client = HubspotClient(settings=_settings(), session=session)

    client.list_properties("tickets")

    assert session.requests[0] == "https://api.hubapi.com/crm/v3/properties/tickets"


def test_list_properties_carries_the_label():
    client = HubspotClient(settings=_settings(), session=_FakeReadSession(_SAMPLE_PAYLOAD))

    props = client.list_properties("contacts")

    by_name = {p["name"]: p["label"] for p in props}
    assert by_name["email"] == "Email"


# --------------------------------------------------------------------------------------
# list_object_types -- standard objects are always included; custom objects only when
# the Private App token has the crm.schemas.custom.read scope (confirmed live to 403
# without it, so a failed schemas call must degrade gracefully, not blow up the picker).
# --------------------------------------------------------------------------------------


class _FakeCallableSession:
    def __init__(self, responder):
        self._responder = responder

    def get(self, url, headers=None, params=None, timeout=None):
        return self._responder(url)


def test_list_object_types_always_includes_standard_objects():
    session = _FakeCallableSession(lambda url: _FakeResponse(403, {"message": "missing scope"}))
    client = HubspotClient(settings=_settings(), session=session)

    types = client.list_object_types()

    names = {t["name"] for t in types}
    assert {"contacts", "companies", "deals"} <= names


def test_list_object_types_degrades_gracefully_without_custom_schema_scope():
    session = _FakeCallableSession(lambda url: _FakeResponse(403, {"message": "missing scope"}))
    client = HubspotClient(settings=_settings(), session=session)

    types = client.list_object_types()

    from src.hubspot_client.api import STANDARD_OBJECT_TYPES

    assert types == STANDARD_OBJECT_TYPES


def test_list_object_types_adds_custom_objects_when_schema_access_is_available():
    schemas_payload = {
        "results": [
            {
                "fullyQualifiedName": "p123_pets",
                "name": "pets",
                "labels": {"singular": "Pet", "plural": "Pets"},
            }
        ]
    }
    session = _FakeCallableSession(lambda url: _FakeResponse(200, schemas_payload))
    client = HubspotClient(settings=_settings(), session=session)

    types = client.list_object_types()

    custom = next(t for t in types if t["name"] == "p123_pets")
    assert custom["label"] == "Pets"
