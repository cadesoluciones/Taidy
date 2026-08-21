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
from src.fabric_pipelines.api import FabricPipelineClient, FabricPipelineError  # noqa: E402
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


class _FakePreviewCursor:
    def __init__(self, description, rows):
        self.description = description
        self._rows = rows
        self.executed_sql = None

    def execute(self, sql):
        self.executed_sql = sql

    def fetchall(self):
        return self._rows


def test_preview_lakehouse_table_returns_columns_and_stringified_rows(settings, monkeypatch):
    """Preview is a on-demand, user-triggered action (unlike the catalog
    listing's non-fatal-by-design list_lakehouse_tables) -- it should
    surface a real value on success: exact column names, and every value
    stringified (None -> "") since native pyodbc values (datetime, Decimal,
    ...) aren't all JSON-serializable as-is and this is just for eyeballing
    structure, not a data export."""
    session = _ScriptedSession([_FakeResponse(200, _SUCCESSFUL_PROPERTIES)])
    client = _client(settings, session)

    description = [("id", None), ("name", None), ("amount", None)]
    rows = [(1, "Alice", None), (2, "Bob", 42)]
    fake_cursor = _FakePreviewCursor(description, rows)
    fake_conn = types.SimpleNamespace(cursor=lambda: fake_cursor, close=lambda: None)
    monkeypatch.setattr(api_module.pyodbc, "connect", lambda *a, **k: fake_conn)

    result = client.preview_lakehouse_table("lh-1", "Lakehouse", "bronze", "bc_customer_list", limit=10)

    assert result == {
        "columns": ["id", "name", "amount"],
        "rows": [["1", "Alice", ""], ["2", "Bob", "42"]],
    }
    assert "TOP 10" in fake_cursor.executed_sql
    assert "[bronze].[bc_customer_list]" in fake_cursor.executed_sql


def test_preview_lakehouse_table_rejects_an_invalid_identifier_without_connecting(settings, monkeypatch):
    """schema/table are meant to come from this same client's own
    list_lakehouse_tables(), but T-SQL has no parameter placeholder for
    identifiers -- anything that isn't a plain [A-Za-z0-9_]+ name is
    rejected before it ever reaches a query string."""
    client = _client(settings, _ScriptedSession([]))
    monkeypatch.setattr(api_module.pyodbc, "connect", lambda *a, **k: pytest.fail("should not connect"))

    with pytest.raises(FabricPipelineError, match="válido"):
        client.preview_lakehouse_table("lh-1", "Lakehouse", "bronze; DROP TABLE x", "bc_customer_list")


def test_preview_lakehouse_table_raises_when_it_cannot_connect(settings, monkeypatch):
    session = _ScriptedSession(
        [_FakeResponse(200, {"properties": {"sqlEndpointProperties": {"provisioningStatus": "InProgress"}}})]
    )
    client = _client(settings, session)

    with pytest.raises(FabricPipelineError, match="conectar"):
        client.preview_lakehouse_table("lh-1", "Lakehouse", "bronze", "bc_customer_list")
