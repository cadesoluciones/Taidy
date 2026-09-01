# -*- coding: utf-8 -*-
"""
Shared pytest fixtures for the webapp/ test suite (Fase 10 / ND-16).

Every fixture here exists to keep these tests fully isolated from the real,
shared application state: webapp/users.db, audit.log, run_history.json,
schedules.json, and workflows.json are NEVER touched -- each test gets its
own throwaway copies under pytest's tmp_path, and the in-memory task/workflow
registries are cleared before and after every test so nothing leaks between
tests within the same process.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from webapp import (  # noqa: E402
    app_settings,
    auth,
    fabric_catalog,
    fabric_catalog_cache,
    history,
    scheduler as sched_module,
    tasks,
    users_db,
    workflow_engine,
    workflows,
)


@pytest.fixture
def isolated_state(tmp_path, monkeypatch):
    """Points every persisted piece of app state at a throwaway directory."""
    monkeypatch.setattr(users_db, "_DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(auth, "_AUDIT_LOG_PATH", tmp_path / "audit.log")
    monkeypatch.setattr(sched_module, "_SCHEDULES_PATH", tmp_path / "schedules.json")
    monkeypatch.setattr(workflows, "_WORKFLOWS_PATH", tmp_path / "workflows.json")
    monkeypatch.setattr(history, "_HISTORY_PATH", tmp_path / "run_history.json")
    monkeypatch.setattr(app_settings, "_SETTINGS_PATH", tmp_path / "app_settings.json")
    monkeypatch.setattr(fabric_catalog, "_CATALOG_PATH", tmp_path / "fabric_catalog.json")
    monkeypatch.setattr(fabric_catalog_cache, "_CACHE_PATH", tmp_path / "fabric_catalog_live_cache.json")
    users_db.init_db()
    # A freshly-seeded admin always has must_change_password=1; clear it so any
    # test using "admin" doesn't need to handle the forced-password-change case
    # unless that's specifically what it's testing.
    users_db.change_password(users_db.DEFAULT_ADMIN_USERNAME, "TestAdminPass2026!", must_change_password=False)

    with tasks._REGISTRY_LOCK:
        tasks._REGISTRY.clear()
    with workflow_engine._REGISTRY_LOCK:
        workflow_engine._REGISTRY.clear()

    yield

    with tasks._REGISTRY_LOCK:
        tasks._REGISTRY.clear()
    with workflow_engine._REGISTRY_LOCK:
        workflow_engine._REGISTRY.clear()


@pytest.fixture
def fake_subprocess(monkeypatch):
    """Swaps the real `python -m src.X ...` launch for a trivial, instant,
    harmless command, so task-launching tests exercise the full orchestration
    (argv building, Task lifecycle, history recording) without ever running
    real extraction/upload code or needing Business Central / Factorial /
    Fabric credentials.
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


def make_user(username: str, password: str, role: str) -> None:
    """Create a user with no forced password change, so a test can log in as
    a non-default-admin role without going through the change-password form.
    """
    users_db.create_user(username, password, role)
    users_db.change_password(username, password, must_change_password=False)
