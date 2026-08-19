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


# --------------------------------------------------------------------------------------
# list_available_tables -- Factorial publishes its full OpenAPI spec live (confirmed:
# GET https://api.factorialhr.com/oas/?version=... works even unauthenticated), unlike
# sample_fields's best-effort data peek. These tests pin the URL, the {id}-path
# filtering, and the prefix-stripping against the real shape observed live.
# --------------------------------------------------------------------------------------

_SAMPLE_SPEC = {
    "openapi": "3.1.0",
    "paths": {
        "/api/2020-01-01/resources/ats/candidates": {
            "get": {"summary": "Reads all Candidates", "tags": ["Ats > Candidate"]},
            "post": {"summary": "Creates a Candidate"},
        },
        "/api/2020-01-01/resources/ats/candidates/{id}": {
            "get": {"summary": "Reads a single Candidate", "tags": ["Ats > Candidate"]},
        },
        "/api/2020-01-01/resources/employees/employees": {
            "get": {"summary": "Reads all Employees", "tags": ["Employees > Employee"]},
        },
        "/api/2020-01-01/resources/employees/employees/{id}/terminate": {
            "post": {"summary": "Terminates an Employee"},
        },
    },
}


def test_list_available_tables_hits_the_oas_endpoint_with_the_configured_version():
    session = _FakeSession(_SAMPLE_SPEC)
    client = FactorialClient(settings=_settings(), session=session)

    client.list_available_tables()

    url, params = session.requests[0]
    assert url == "https://api.factorialhr.com/oas/"
    assert params == [("version", "2020-01-01")]


def test_list_available_tables_excludes_paths_with_id_parameters():
    client = FactorialClient(settings=_settings(), session=_FakeSession(_SAMPLE_SPEC))

    tables = client.list_available_tables()

    names = {t["name"] for t in tables}
    assert "resources/ats/candidates/{id}" not in names
    assert "resources/employees/employees/{id}/terminate" not in names


def test_list_available_tables_excludes_paths_without_a_get_method():
    spec = {"paths": {"/api/2020-01-01/resources/x": {"post": {"summary": "Creates X"}}}}
    client = FactorialClient(settings=_settings(), session=_FakeSession(spec))

    assert client.list_available_tables() == []


def test_list_available_tables_strips_the_version_prefix():
    client = FactorialClient(settings=_settings(), session=_FakeSession(_SAMPLE_SPEC))

    tables = client.list_available_tables()

    names = {t["name"] for t in tables}
    assert "resources/ats/candidates" in names
    assert "resources/employees/employees" in names


def test_list_available_tables_builds_label_from_tag_and_summary():
    client = FactorialClient(settings=_settings(), session=_FakeSession(_SAMPLE_SPEC))

    tables = client.list_available_tables()

    candidates = next(t for t in tables if t["name"] == "resources/ats/candidates")
    assert candidates["label"] == "Ats > Candidate — Reads all Candidates"


def test_list_available_tables_sorted_by_name():
    client = FactorialClient(settings=_settings(), session=_FakeSession(_SAMPLE_SPEC))

    tables = client.list_available_tables()

    assert [t["name"] for t in tables] == sorted(t["name"] for t in tables)
