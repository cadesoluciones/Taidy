# -*- coding: utf-8 -*-
"""
FabricPipelineClient.list_lakehouse_tables() -- a Lakehouse's own tables
(bronze./gold. schema-qualified names) aren't Fabric workspace items, so
they're not returned by list_items(); confirmed live against the real
workspace that the REST "list tables" endpoint itself fails for a
schema-enabled Lakehouse (HTTP 400, errorCode
UnsupportedOperationForSchemasEnabledLakehouse). The only path that works
for both schema-enabled and legacy Lakehouses is the SQL analytics endpoint
every Lakehouse exposes, queried via pyodbc with an AAD access token
(same service principal, SQL token audience instead of the Fabric one).
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import src.fabric_pipelines.api as api_module  # noqa: E402
from src.fabric_pipelines.api import FabricPipelineClient  # noqa: E402
from src.fabric_pipelines.config import Settings  # noqa: E402


class _FakeResponse:
    def __init__(self, status_code, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text

    def json(self):
        return self._json_data


class _ScriptedSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.requests = []

    def request(self, method, url, **kwargs):
        self.requests.append({"method": method, "url": url})
        return self._responses.pop(0)


_SUCCESSFUL_PROPERTIES = {
    "properties": {
        "sqlEndpointProperties": {
            "connectionString": "abc123.datawarehouse.fabric.microsoft.com",
            "provisioningStatus": "Success",
        }
    }
}


@pytest.fixture
def settings() -> Settings:
    return Settings(tenant_id="t", client_id="c", client_secret="s", workspace_id="ws-1", pipelines=[])


def _client(settings, session) -> FabricPipelineClient:
    client = FabricPipelineClient(settings=settings, session=session)
    client._headers = lambda: {}
    client._sql_access_token_struct = lambda: b"token"
    return client


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows
        self.executed_sql = None

    def execute(self, sql):
        self.executed_sql = sql

    def fetchall(self):
        return self._rows


class _FakeConnection:
    def __init__(self, rows):
        self._cursor = _FakeCursor(rows)
        self.closed = False

    def cursor(self):
        return self._cursor

    def close(self):
        self.closed = True


def _row(schema, table):
    return types.SimpleNamespace(schema_name=schema, table_name=table)


def test_list_lakehouse_tables_queries_the_sql_endpoint_and_maps_rows(settings, monkeypatch):
    session = _ScriptedSession([_FakeResponse(200, _SUCCESSFUL_PROPERTIES)])
    client = _client(settings, session)

    fake_conn = _FakeConnection([_row("bronze", "bc_cuentas_contables"), _row("gold", "ventas_resumen")])
    captured = {}

    def fake_connect(conn_str, attrs_before=None, timeout=None):
        captured["conn_str"] = conn_str
        captured["attrs_before"] = attrs_before
        return fake_conn

    monkeypatch.setattr(api_module.pyodbc, "connect", fake_connect)

    tables = client.list_lakehouse_tables("lh-1", "Lakehouse")

    assert tables == [
        {"schema": "bronze", "table": "bc_cuentas_contables"},
        {"schema": "gold", "table": "ventas_resumen"},
    ]
    assert "abc123.datawarehouse.fabric.microsoft.com" in captured["conn_str"]
    assert "DATABASE=Lakehouse" in captured["conn_str"]
    assert api_module._SQL_COPT_SS_ACCESS_TOKEN in captured["attrs_before"]
    assert fake_conn.closed is True  # never leaks the connection, even on the happy path


def test_list_lakehouse_tables_returns_empty_when_the_detail_request_fails(settings, monkeypatch):
    session = _ScriptedSession([_FakeResponse(403, text="Forbidden")])
    client = _client(settings, session)
    monkeypatch.setattr(api_module.pyodbc, "connect", lambda *a, **k: pytest.fail("should not connect"))

    assert client.list_lakehouse_tables("lh-1", "Lakehouse") == []


def test_list_lakehouse_tables_returns_empty_when_the_sql_endpoint_is_not_provisioned(settings, monkeypatch):
    session = _ScriptedSession(
        [_FakeResponse(200, {"properties": {"sqlEndpointProperties": {"provisioningStatus": "InProgress"}}})]
    )
    client = _client(settings, session)
    monkeypatch.setattr(api_module.pyodbc, "connect", lambda *a, **k: pytest.fail("should not connect"))

    assert client.list_lakehouse_tables("lh-1", "Lakehouse") == []


def test_list_lakehouse_tables_returns_empty_on_a_pyodbc_connection_error(settings, monkeypatch):
    """Non-fatal by design -- one Lakehouse this service principal can't
    reach (or isn't done provisioning) shouldn't blank out the rest of the
    catalog, which merges several independent sources."""
    session = _ScriptedSession([_FakeResponse(200, _SUCCESSFUL_PROPERTIES)])
    client = _client(settings, session)

    def raise_pyodbc_error(*args, **kwargs):
        raise api_module.pyodbc.Error("login failed")

    monkeypatch.setattr(api_module.pyodbc, "connect", raise_pyodbc_error)

    assert client.list_lakehouse_tables("lh-1", "Lakehouse") == []
