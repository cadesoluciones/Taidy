# -*- coding: utf-8 -*-
"""
FabricPipelineClient.get_definition() fetches a Data Pipeline's activities
and dependencies -- used to draw the pipeline as a diagram. Fabric's
getDefinition endpoint can return either an immediate 200 or a long-running
operation (202 + Location to poll, then GET .../result); both paths are
covered here with a fake session, never a real network call. parse_pipeline_
definition()/extract_activities() are pure functions covered directly with
literal ADF-style payloads.
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.fabric_pipelines.api import (  # noqa: E402
    FabricPipelineClient,
    FabricPipelineError,
    extract_activities,
    parse_pipeline_definition,
)
from src.fabric_pipelines.config import Settings  # noqa: E402


def _encode_definition(pipeline_json: dict) -> dict:
    payload = base64.b64encode(json.dumps(pipeline_json).encode("utf-8")).decode("ascii")
    return {"definition": {"parts": [{"path": "pipeline-content.json", "payload": payload, "payloadType": "InlineBase64"}]}}


_SAMPLE_PIPELINE = {
    "properties": {
        "activities": [
            {"name": "ExtractBC", "type": "Copy", "dependsOn": []},
            {
                "name": "UploadBC",
                "type": "Copy",
                "dependsOn": [{"activity": "ExtractBC", "dependencyConditions": ["Succeeded"]}],
            },
            {
                "name": "Notify",
                "type": "WebActivity",
                "dependsOn": [{"activity": "UploadBC", "dependencyConditions": ["Failed", "Succeeded"]}],
            },
        ]
    }
}


class _FakeResponse:
    def __init__(self, status_code, headers=None, json_data=None, text=""):
        self.status_code = status_code
        self.headers = headers or {}
        self._json_data = json_data
        self.text = text

    def json(self):
        return self._json_data


class _FakeSession:
    """Scripted sequence of responses, one per call to .request(), in order."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url))
        return self._responses.pop(0)


@pytest.fixture
def settings() -> Settings:
    return Settings(tenant_id="t", client_id="c", client_secret="s", workspace_id="ws", pipelines=[])


def _client(settings: Settings, session) -> FabricPipelineClient:
    client = FabricPipelineClient(settings, session=session)
    client._headers = lambda: {}
    return client


def test_get_definition_returns_immediately_on_200(settings):
    definition_payload = _encode_definition(_SAMPLE_PIPELINE)
    session = _FakeSession([_FakeResponse(200, json_data=definition_payload)])
    client = _client(settings, session)

    result = client.get_definition("item-1")

    assert result == definition_payload
    assert len(session.calls) == 1


def test_get_definition_polls_a_long_running_operation(settings, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    definition_payload = _encode_definition(_SAMPLE_PIPELINE)
    session = _FakeSession(
        [
            _FakeResponse(202, headers={"Location": "https://x/operations/op-1", "Retry-After": "1"}),
            _FakeResponse(200, json_data={"status": "Running"}),
            _FakeResponse(200, json_data={"status": "Succeeded"}),
            _FakeResponse(200, json_data=definition_payload),
        ]
    )
    client = _client(settings, session)

    result = client.get_definition("item-1")

    assert result == definition_payload
    assert session.calls[-1] == ("GET", "https://x/operations/op-1/result")


def test_get_definition_raises_when_the_operation_fails(settings, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    session = _FakeSession(
        [
            _FakeResponse(202, headers={"Location": "https://x/operations/op-1"}),
            _FakeResponse(200, json_data={"status": "Failed", "error": "boom"}),
        ]
    )
    client = _client(settings, session)

    with pytest.raises(FabricPipelineError, match="boom"):
        client.get_definition("item-1")


def test_get_definition_raises_on_a_bad_status(settings):
    session = _FakeSession([_FakeResponse(403, text="forbidden")])
    client = _client(settings, session)

    with pytest.raises(FabricPipelineError, match="403"):
        client.get_definition("item-1")


def test_parse_pipeline_definition_decodes_the_content_part():
    definition_payload = _encode_definition(_SAMPLE_PIPELINE)

    assert parse_pipeline_definition(definition_payload) == _SAMPLE_PIPELINE


def test_parse_pipeline_definition_raises_when_content_part_missing():
    with pytest.raises(FabricPipelineError, match="pipeline-content.json"):
        parse_pipeline_definition({"definition": {"parts": []}})


def test_extract_activities_maps_dependencies_by_name():
    activities = extract_activities(_SAMPLE_PIPELINE)

    assert [a["name"] for a in activities] == ["ExtractBC", "UploadBC", "Notify"]
    assert activities[0]["depends_on"] == []
    assert activities[1]["depends_on"] == [{"activity": "ExtractBC", "conditions": ["Succeeded"]}]
    assert activities[2]["type"] == "WebActivity"


def test_extract_activities_on_empty_pipeline_returns_empty_list():
    assert extract_activities({"properties": {"activities": []}}) == []
