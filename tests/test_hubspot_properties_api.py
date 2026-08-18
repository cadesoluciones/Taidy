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
