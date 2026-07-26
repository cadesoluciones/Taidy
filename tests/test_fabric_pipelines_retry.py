# -*- coding: utf-8 -*-
"""
Fabric pipeline runs go through a single HTTP call each (trigger/poll/list)
with no retry -- unlike src/bc_client/api.py and src/factorial_client/api.py,
which already retry transient network errors (dropped connection, timeout)
with exponential backoff. A token refresh race or a network blip mid-run used
to raise straight through and fail the whole pipeline launch.

FabricPipelineClient._request now shares that same tenacity policy. These
tests prove it actually retries (and still gives up once exhausted) instead
of asserting "the decorator is there" by inspection.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import requests

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.fabric_pipelines.api import FabricPipelineClient, FabricPipelineError  # noqa: E402
from src.fabric_pipelines.config import Settings  # noqa: E402


class _FakeResponse:
    def __init__(self, status_code, headers=None, json_data=None, text=""):
        self.status_code = status_code
        self.headers = headers or {}
        self._json_data = json_data
        self.text = text

    def json(self):
        return self._json_data


class _FlakySession:
    """Raises a transient network error `fail_times` times, then succeeds."""

    def __init__(self, fail_times, response, exc=None):
        self.fail_times = fail_times
        self.response = response
        self.exc = exc or requests.ConnectionError("simulated drop")
        self.calls = 0

    def request(self, method, url, **kwargs):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise self.exc
        return self.response


@pytest.fixture
def settings() -> Settings:
    return Settings(tenant_id="t", client_id="c", client_secret="s", workspace_id="ws", pipelines=[])


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    # tenacity's wait_exponential would otherwise really sleep between
    # attempts (up to ~30s total across 5 attempts) -- keep the test fast.
    monkeypatch.setattr("time.sleep", lambda _seconds: None)


def _client(settings: Settings, session: _FlakySession) -> FabricPipelineClient:
    client = FabricPipelineClient(settings, session=session)
    client._headers = lambda: {}  # skip the real ClientSecretCredential network call
    return client


def test_trigger_run_retries_a_transient_drop_then_succeeds(settings):
    response = _FakeResponse(202, headers={"Location": "https://x/jobs/instances/job-123"})
    session = _FlakySession(fail_times=2, response=response)
    client = _client(settings, session)

    job_id = client.trigger_run("item-1")

    assert job_id == "job-123"
    assert session.calls == 3  # 2 failures + 1 success


def test_trigger_run_gives_up_after_exhausting_retries(settings):
    session = _FlakySession(fail_times=10, response=_FakeResponse(202))
    client = _client(settings, session)

    with pytest.raises(requests.ConnectionError):
        client.trigger_run("item-1")

    assert session.calls == 5  # stop_after_attempt(5)


def test_get_status_retries_a_timeout(settings):
    response = _FakeResponse(200, json_data={"status": "Completed"})
    session = _FlakySession(fail_times=1, response=response, exc=requests.Timeout("slow"))
    client = _client(settings, session)

    status = client.get_status("item-1", "job-1")

    assert status == {"status": "Completed"}
    assert session.calls == 2


def test_bad_http_status_is_not_retried(settings):
    """A real Fabric-side rejection (bad auth, 404, ...) must raise
    immediately -- retrying it would waste 5 attempts on an error retrying
    can never fix."""
    session = _FlakySession(fail_times=0, response=_FakeResponse(403, text="forbidden"))
    client = _client(settings, session)

    with pytest.raises(FabricPipelineError):
        client.trigger_run("item-1")

    assert session.calls == 1
