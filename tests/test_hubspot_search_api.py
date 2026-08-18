# -*- coding: utf-8 -*-
"""
src/hubspot_client/api.py::search_table_with_ids -- the sync engine's
incremental fetch depends on this hitting the CRM Search API with the exact
body shape HubSpot expects (epoch-milliseconds date filter, not the ISO
string a normal read returns). This was live-verified against a real
HubSpot portal; these tests pin the request/response contract down so a
future change can't silently drift from what was actually confirmed to
work.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.hubspot_client.api import HubspotClient  # noqa: E402
from src.hubspot_client.config import Settings, TableConfig  # noqa: E402


def _settings() -> Settings:
    return Settings(base_url="https://api.hubapi.com", api_key="fake-key", tables=[])


class _FakeResponse:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


class _FakeSearchSession:
    def __init__(self, pages):
        self._pages = list(pages)
        self.requests = []

    def post(self, url, headers=None, json=None, timeout=None):
        self.requests.append((url, json))
        return _FakeResponse(200, self._pages.pop(0))

    def get(self, *args, **kwargs):  # pragma: no cover - unused here
        raise NotImplementedError


def test_search_table_with_ids_sends_epoch_ms_filter_and_sort():
    table = TableConfig(name="hubspot_contacts", object_type="contacts", fields=["email", "firstname"])
    session = _FakeSearchSession([{"results": [{"id": "1", "properties": {"email": "a@example.com", "firstname": "Ana"}}]}])
    client = HubspotClient(settings=_settings(), session=session)

    rows = client.search_table_with_ids(table, date_field="lastmodifieddate", modified_since_epoch_ms=1750000000000)

    assert rows == [{"email": "a@example.com", "firstname": "Ana", "__hubspot_id": "1"}]

    url, body = session.requests[0]
    assert url == "https://api.hubapi.com/crm/v3/objects/contacts/search"
    assert body["filterGroups"] == [
        {"filters": [{"propertyName": "lastmodifieddate", "operator": "GT", "value": "1750000000000"}]}
    ]
    assert body["sorts"] == [{"propertyName": "lastmodifieddate", "direction": "ASCENDING"}]
    assert body["properties"] == ["email", "firstname"]
    assert "after" not in body


def test_search_table_with_ids_paginates_using_cursor():
    table = TableConfig(name="hubspot_contacts", object_type="contacts", fields=["email"])
    session = _FakeSearchSession(
        [
            {
                "results": [{"id": "1", "properties": {"email": "a@example.com"}}],
                "paging": {"next": {"after": "cursor-1"}},
            },
            {"results": [{"id": "2", "properties": {"email": "b@example.com"}}]},
        ]
    )
    client = HubspotClient(settings=_settings(), session=session)

    rows = client.search_table_with_ids(table, date_field="lastmodifieddate", modified_since_epoch_ms=0)

    assert [r["__hubspot_id"] for r in rows] == ["1", "2"]
    assert "after" not in session.requests[0][1]
    assert session.requests[1][1]["after"] == "cursor-1"


def test_search_table_with_ids_returns_empty_list_when_nothing_matches():
    table = TableConfig(name="hubspot_contacts", object_type="contacts", fields=["email"])
    session = _FakeSearchSession([{"results": []}])
    client = HubspotClient(settings=_settings(), session=session)

    rows = client.search_table_with_ids(table, date_field="lastmodifieddate", modified_since_epoch_ms=9999999999999)

    assert rows == []
