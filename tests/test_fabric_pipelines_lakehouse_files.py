# -*- coding: utf-8 -*-
"""
FabricPipelineClient.read_lakehouse_file()/write_lakehouse_file() -- plain
text files under a Lakehouse's own Files/ area (e.g.
catalog_manifests/<table>.yml, a YAML data-contract manifest a
catalog_metadata notebook reads to (re)generate its catalog.<table> Delta
table from) via OneLake's ADLS Gen2-compatible DFS API. A different surface
entirely from the Fabric REST API (list_items, get_definition) and the SQL
analytics endpoint (Tables/ only, read-only) -- confirmed live against the
real workspace (full create/write/read-back/delete round trip) before this
was written; these tests pin that contract with a fake session, no live call.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.fabric_pipelines.api import FabricPipelineClient, FabricPipelineError  # noqa: E402
from src.fabric_pipelines.config import Settings  # noqa: E402


class _FakeResponse:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text


class _ScriptedSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.requests = []

    def request(self, method, url, **kwargs):
        self.requests.append({"method": method, "url": url, **kwargs})
        return self._responses.pop(0)


@pytest.fixture
def settings() -> Settings:
    return Settings(tenant_id="t", client_id="c", client_secret="s", workspace_id="ws-1", pipelines=[])


def _client(settings, session) -> FabricPipelineClient:
    client = FabricPipelineClient(settings=settings, session=session)
    client._storage_headers = lambda: {}
    return client


def test_read_lakehouse_file_returns_the_text_content(settings):
    session = _ScriptedSession([_FakeResponse(200, text="step:\n  name: bronze_bc_customer\n")])
    client = _client(settings, session)

    content = client.read_lakehouse_file("lh-1", "catalog_manifests/bronze_bc_customer.yml")

    assert content == "step:\n  name: bronze_bc_customer\n"
    assert session.requests[0]["method"] == "GET"
    assert session.requests[0]["url"] == "https://onelake.dfs.fabric.microsoft.com/ws-1/lh-1/Files/catalog_manifests/bronze_bc_customer.yml"


def test_read_lakehouse_file_returns_none_for_a_missing_file(settings):
    session = _ScriptedSession([_FakeResponse(404, text="not found")])
    client = _client(settings, session)

    assert client.read_lakehouse_file("lh-1", "catalog_manifests/does_not_exist.yml") is None


def test_read_lakehouse_file_raises_on_an_unexpected_status(settings):
    session = _ScriptedSession([_FakeResponse(403, text="forbidden")])
    client = _client(settings, session)

    with pytest.raises(FabricPipelineError, match="403"):
        client.read_lakehouse_file("lh-1", "x.yml")


def test_write_lakehouse_file_does_the_create_append_flush_sequence(settings):
    session = _ScriptedSession([_FakeResponse(201), _FakeResponse(202), _FakeResponse(200)])
    client = _client(settings, session)

    client.write_lakehouse_file("lh-1", "catalog_manifests/bronze_bc_customer.yml", "step:\n  name: x\n")

    assert [r["method"] for r in session.requests] == ["PUT", "PATCH", "PATCH"]
    assert session.requests[0]["params"] == {"resource": "file"}
    assert session.requests[1]["params"] == {"action": "append", "position": "0"}
    assert session.requests[1]["data"] == "step:\n  name: x\n".encode("utf-8")
    assert session.requests[2]["params"] == {"action": "flush", "position": str(len("step:\n  name: x\n".encode("utf-8")))}


def test_write_lakehouse_file_raises_if_create_fails(settings):
    session = _ScriptedSession([_FakeResponse(403, text="forbidden")])
    client = _client(settings, session)

    with pytest.raises(FabricPipelineError, match="403"):
        client.write_lakehouse_file("lh-1", "x.yml", "content")


def test_write_lakehouse_file_raises_if_append_fails(settings):
    session = _ScriptedSession([_FakeResponse(201), _FakeResponse(500, text="server error")])
    client = _client(settings, session)

    with pytest.raises(FabricPipelineError, match="500"):
        client.write_lakehouse_file("lh-1", "x.yml", "content")


def test_write_lakehouse_file_raises_if_flush_fails(settings):
    session = _ScriptedSession([_FakeResponse(201), _FakeResponse(202), _FakeResponse(409, text="conflict")])
    client = _client(settings, session)

    with pytest.raises(FabricPipelineError, match="409"):
        client.write_lakehouse_file("lh-1", "x.yml", "content")
