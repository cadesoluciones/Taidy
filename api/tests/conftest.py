# -*- coding: utf-8 -*-
"""
Same isolation discipline as webapp/tests/conftest.py: every test gets a
throwaway users.db/audit.log under pytest's tmp_path, and the in-memory
session store is cleared before and after every test. The real
webapp/users.db and webapp/audit.log are never touched.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from webapp import auth, users_db  # noqa: E402

from api import dependencies as deps  # noqa: E402
from api.main import app  # noqa: E402


@pytest.fixture
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setattr(users_db, "_DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(auth, "_AUDIT_LOG_PATH", tmp_path / "audit.log")
    users_db.init_db()

    with deps._SESSIONS_LOCK:
        deps._SESSIONS.clear()

    yield

    with deps._SESSIONS_LOCK:
        deps._SESSIONS.clear()


@pytest.fixture
def client():
    return TestClient(app)
