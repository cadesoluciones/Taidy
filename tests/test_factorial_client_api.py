# -*- coding: utf-8 -*-
"""
src/factorial_client/api.py::sample_fields -- Factorial has no schema/
properties endpoint like HubSpot's, so this is a best-effort "peek": fetch
one small page of real data and return the union of keys actually seen.
These tests pin the request shape (date_range params) and the union/sample
-size behavior with a fake session -- no live calls.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.factorial_client.api import FactorialClient  # noqa: E402
from src.factorial_client.config import Settings  # noqa: E402


def _settings() -> Settings:
    return Settings(api_key="fake-key", api_version="2020-01-01", tables=[])


class _FakeResponse:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, payload):
        self._payload = payload
        self.requests = []

    def get(self, url, headers=None, params=None, timeout=None):
        self.requests.append((url, params))
        return _FakeResponse(200, self._payload)


def test_sample_fields_returns_union_of_keys_across_sampled_records():
    payload = {"data": [{"id": 1, "email": "a@x.com"}, {"id": 2, "active": True}]}
    client = FactorialClient(settings=_settings(), session=_FakeSession(payload))

    names = client.sample_fields(path="resources/employees/employees")

    assert names == ["active", "email", "id"]


def test_sample_fields_sends_date_range_params_when_requested():
    payload = {"data": []}
    session = _FakeSession(payload)
    client = FactorialClient(settings=_settings(), session=session)

    client.sample_fields(path="resources/employees/employees", date_range=True)

    url, params = session.requests[0]
    assert url == "https://api.factorialhr.com/api/2020-01-01/resources/employees/employees"
    param_keys = [p[0] for p in params]
    assert "start_on" in param_keys
    assert "end_on" in param_keys


def test_sample_fields_omits_date_params_by_default():
    payload = {"data": []}
    session = _FakeSession(payload)
    client = FactorialClient(settings=_settings(), session=session)

    client.sample_fields(path="resources/employees/employees")

    assert session.requests[0][1] == []


def test_sample_fields_only_inspects_up_to_the_sample_size():
    from src.factorial_client.api import _SAMPLE_SIZE

    payload = {"data": [{f"field_{i}": i} for i in range(_SAMPLE_SIZE + 5)]}
    client = FactorialClient(settings=_settings(), session=_FakeSession(payload))

    names = client.sample_fields(path="resources/employees/employees")

    assert len(names) == _SAMPLE_SIZE


def test_sample_fields_returns_empty_list_when_no_data():
    payload = {"data": []}
    client = FactorialClient(settings=_settings(), session=_FakeSession(payload))

    assert client.sample_fields(path="resources/employees/employees") == []
