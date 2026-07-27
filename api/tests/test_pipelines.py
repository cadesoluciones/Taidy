# -*- coding: utf-8 -*-
"""
GET /pipelines/{name}/dependencies -- Operator/Admin gated (matches
/ejecutar/pipelines, the page it backs). Fabric itself is never called in
these tests: `load_settings` and `FabricPipelineClient` are monkeypatched at
the api.routers.pipelines import site, so nothing here needs real Fabric
credentials or makes a real network call.
"""

from __future__ import annotations

from src.fabric_pipelines.api import FabricPipelineError
from src.fabric_pipelines.config import PipelineConfig, Settings
from webapp import users_db
from webapp.tests.conftest import make_user

from api.routers import pipelines as pipelines_router


def _login(client, username, password):
    assert client.post("/auth/login", json={"username": username, "password": password}).status_code == 200


_SETTINGS = Settings(
    tenant_id="t",
    client_id="c",
    client_secret="s",
    workspace_id="ws",
    pipelines=[PipelineConfig(name="Pipeline_CADE_Bronce", item_id="item-1")],
)


class _FakeClient:
    def __init__(self, *a, **k):
        pass

    def get_definition(self, item_id):
        return {"item_id": item_id}


def test_reader_cannot_view_pipeline_dependencies(isolated_state, client):
    make_user("reader1", "ReaderPass2026!", users_db.ROLE_READER)
    _login(client, "reader1", "ReaderPass2026!")

    resp = client.get("/pipelines/Pipeline_CADE_Bronce/dependencies")
    assert resp.status_code == 403


def test_returns_400_when_fabric_is_not_configured(isolated_state, client, monkeypatch):
    def _raise(*a, **k):
        raise ValueError("FABRIC_CLIENT_SECRET no está definida")

    monkeypatch.setattr(pipelines_router, "load_settings", _raise)
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    resp = client.get("/pipelines/Pipeline_CADE_Bronce/dependencies")
    assert resp.status_code == 400


def test_returns_404_for_an_unknown_pipeline_name(isolated_state, client, monkeypatch):
    monkeypatch.setattr(pipelines_router, "load_settings", lambda: _SETTINGS)
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    resp = client.get("/pipelines/does-not-exist/dependencies")
    assert resp.status_code == 404


def test_returns_502_when_the_fabric_call_fails(isolated_state, client, monkeypatch):
    monkeypatch.setattr(pipelines_router, "load_settings", lambda: _SETTINGS)

    class _FailingClient:
        def __init__(self, *a, **k):
            pass

        def get_definition(self, item_id):
            raise FabricPipelineError("boom")

    monkeypatch.setattr(pipelines_router, "FabricPipelineClient", _FailingClient)
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    resp = client.get("/pipelines/Pipeline_CADE_Bronce/dependencies")
    assert resp.status_code == 502


def test_operator_can_view_the_dependency_graph(isolated_state, client, monkeypatch):
    monkeypatch.setattr(pipelines_router, "load_settings", lambda: _SETTINGS)
    monkeypatch.setattr(pipelines_router, "FabricPipelineClient", _FakeClient)
    monkeypatch.setattr(
        pipelines_router,
        "parse_pipeline_definition",
        lambda definition: {
            "properties": {
                "activities": [
                    {"name": "Extract", "type": "Copy", "dependsOn": []},
                    {
                        "name": "Upload",
                        "type": "Copy",
                        "dependsOn": [{"activity": "Extract", "dependencyConditions": ["Succeeded"]}],
                    },
                ]
            }
        },
    )
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    _login(client, "operator1", "OperatorPass2026!")

    resp = client.get("/pipelines/Pipeline_CADE_Bronce/dependencies")
    assert resp.status_code == 200
    body = resp.json()
    assert [a["name"] for a in body["activities"]] == ["Extract", "Upload"]
    assert body["activities"][1]["depends_on"] == [{"activity": "Extract", "conditions": ["Succeeded"]}]
