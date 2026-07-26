# -*- coding: utf-8 -*-
"""
state_path() lets every persisted file (users.db, audit.log, schedules.json,
workflows.json, run_history.json) move into a mounted volume in Docker via
one TAIDY_STATE_DIR env var, without changing local-dev behavior when it's
unset -- see webapp/state_dir.py.
"""

from __future__ import annotations

from pathlib import Path

from webapp.state_dir import state_path


def test_state_path_defaults_to_given_dir_when_env_unset(monkeypatch):
    monkeypatch.delenv("TAIDY_STATE_DIR", raising=False)
    default_dir = Path("/some/module/dir")
    assert state_path("users.db", default_dir) == default_dir / "users.db"


def test_state_path_uses_env_override_when_set(monkeypatch, tmp_path):
    monkeypatch.setenv("TAIDY_STATE_DIR", str(tmp_path))
    default_dir = Path("/some/module/dir")
    assert state_path("users.db", default_dir) == tmp_path / "users.db"
