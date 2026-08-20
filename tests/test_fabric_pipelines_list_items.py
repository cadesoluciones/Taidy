# -*- coding: utf-8 -*-
"""
FabricPipelineClient.list_items()/list_folders() -- generalizes the existing
list_pipelines() (which filters to type=DataPipeline) to fetch every item
type, plus the folder tree, so webapp/fabric_catalog.py can rebuild each
item's real "ETLs Medallion/silver"-style path. Response shapes reproduced
live against the real Fabric workspace before writing this.
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
    def __init__(self, status_code, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text

    def json(self):
        return self._json_data


class _ScriptedSession:
    """Returns one fixed response per call, in order -- for pagination tests."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.requests = []

    def request(self, method, url, **kwargs):
        self.requests.append({"method": method, "url": url, "params": kwargs.get("params")})
        return self._responses.pop(0)


@pytest.fixture
def settings() -> Settings:
    return Settings(tenant_id="t", client_id="c", client_secret="s", workspace_id="ws-1", pipelines=[])


def _client(settings, session) -> FabricPipelineClient:
    client = FabricPipelineClient(settings=settings, session=session)
    client._headers = lambda: {}  # skip the real ClientSecretCredential network call
    return client


def test_list_items_returns_every_type_with_no_type_filter(settings):
    session = _ScriptedSession(
        [
            _FakeResponse(
                200,
                {
                    "value": [
                        {"id": "nb-1", "type": "Notebook", "displayName": "silver_facturas", "folderId": "f1"},
                        {"id": "pl-1", "type": "DataPipeline", "displayName": "Pipeline_CADE_Bronce"},
                    ]
                },
            )
        ]
    )
    client = _client(settings, session)

    items = client.list_items()

    assert [i["id"] for i in items] == ["nb-1", "pl-1"]
    # No `type` filter, unlike list_pipelines() -- confirms every item type comes back.
    assert session.requests[0]["params"] == {}


def test_list_items_follows_continuation_token_across_pages(settings):
    session = _ScriptedSession(
        [
            _FakeResponse(200, {"value": [{"id": "a"}], "continuationToken": "page2"}),
            _FakeResponse(200, {"value": [{"id": "b"}]}),
        ]
    )
    client = _client(settings, session)

    items = client.list_items()

    assert [i["id"] for i in items] == ["a", "b"]
    assert session.requests[1]["params"] == {"continuationToken": "page2"}


def test_list_items_raises_on_a_non_200_response(settings):
    session = _ScriptedSession([_FakeResponse(403, text="Forbidden")])
    client = _client(settings, session)

    with pytest.raises(FabricPipelineError, match="403"):
        client.list_items()


def test_list_folders_returns_the_tree_with_parent_ids(settings):
    session = _ScriptedSession(
        [
            _FakeResponse(
                200,
                {
                    "value": [
                        {"id": "f-root", "displayName": "ETLs Medallion"},
                        {"id": "f-silver", "displayName": "silver", "parentFolderId": "f-root"},
                    ]
                },
            )
        ]
    )
    client = _client(settings, session)

    folders = client.list_folders()

    assert folders[0]["displayName"] == "ETLs Medallion"
    assert "parentFolderId" not in folders[0]
    assert folders[1]["parentFolderId"] == "f-root"


def test_list_folders_follows_continuation_token_across_pages(settings):
    session = _ScriptedSession(
        [
            _FakeResponse(200, {"value": [{"id": "f1", "displayName": "A"}], "continuationToken": "page2"}),
            _FakeResponse(200, {"value": [{"id": "f2", "displayName": "B"}]}),
        ]
    )
    client = _client(settings, session)

    folders = client.list_folders()

    assert [f["id"] for f in folders] == ["f1", "f2"]


def test_list_folders_raises_on_a_non_200_response(settings):
    session = _ScriptedSession([_FakeResponse(500, text="Internal error")])
    client = _client(settings, session)

    with pytest.raises(FabricPipelineError, match="500"):
        client.list_folders()
