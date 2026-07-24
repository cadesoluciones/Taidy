# -*- coding: utf-8 -*-
"""
Same isolation discipline as webapp/tests/conftest.py: every test gets
throwaway users.db/audit.log/schedules.json/run_history.json/workflows.json
under pytest's tmp_path, and every in-memory registry (sessions, tasks,
workflow runs) is cleared before and after every test. The real
webapp/users.db, audit.log, and friends are never touched.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from webapp import (  # noqa: E402
    auth,
    history,
    scheduler as sched_module,
    tasks,
    users_db,
    workflow_engine,
    workflows,
)

from api import dependencies as deps  # noqa: E402
from api.main import app  # noqa: E402


@pytest.fixture
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setattr(users_db, "_DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(auth, "_AUDIT_LOG_PATH", tmp_path / "audit.log")
    monkeypatch.setattr(sched_module, "_SCHEDULES_PATH", tmp_path / "schedules.json")
    monkeypatch.setattr(workflows, "_WORKFLOWS_PATH", tmp_path / "workflows.json")
    monkeypatch.setattr(history, "_HISTORY_PATH", tmp_path / "run_history.json")
    users_db.init_db()

    with deps._SESSIONS_LOCK:
        deps._SESSIONS.clear()
    with tasks._REGISTRY_LOCK:
        tasks._REGISTRY.clear()
    with workflow_engine._REGISTRY_LOCK:
        workflow_engine._REGISTRY.clear()

    yield

    with deps._SESSIONS_LOCK:
        deps._SESSIONS.clear()
    with tasks._REGISTRY_LOCK:
        tasks._REGISTRY.clear()
    with workflow_engine._REGISTRY_LOCK:
        workflow_engine._REGISTRY.clear()


@pytest.fixture
def client():
    # Context-managed so the lifespan hook runs (app.state.scheduler must
    # exist for the /schedules endpoints).
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def fake_subprocess(monkeypatch):
    """Same stand-in as webapp/tests/conftest.py's fixture of the same name
    (duplicated, not imported: pytest fixtures don't cross sibling conftest
    trees) -- swaps the real `python -m src.X ...` launch for a trivial,
    instant, harmless command.
    """

    def _fake_popen(module: str, argv: list) -> subprocess.Popen:
        return subprocess.Popen(
            [sys.executable, "-c", "print('fake output')"],
            cwd=str(_PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

    monkeypatch.setattr(tasks, "_popen", _fake_popen)
