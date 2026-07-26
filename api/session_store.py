# -*- coding: utf-8 -*-
"""
Persisted session store for the FastAPI cookie session (session_id ->
username).

Plain JSON file, read fresh and written through on every call -- the same
"file is the single source of truth, no in-memory cache" pattern
webapp/scheduler.py/workflows.py/history.py already use, so a restart no
longer logs out every signed-in user (the previous in-memory-only dict did).
Kept out of webapp/ since sessions are a FastAPI-only concept.
"""

from __future__ import annotations

import json
import secrets
import threading
from pathlib import Path
from typing import Dict, Optional

from webapp.state_dir import state_path

_SESSIONS_PATH = state_path("sessions.json", Path(__file__).resolve().parent)
_LOCK = threading.Lock()


def _read() -> Dict[str, str]:
    if not _SESSIONS_PATH.is_file():
        return {}
    try:
        data = json.loads(_SESSIONS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _write(sessions: Dict[str, str]) -> None:
    tmp = _SESSIONS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(sessions), encoding="utf-8")
    tmp.replace(_SESSIONS_PATH)


def create_session(username: str) -> str:
    session_id = secrets.token_urlsafe(32)
    with _LOCK:
        sessions = _read()
        sessions[session_id] = username
        _write(sessions)
    return session_id


def get_session_username(session_id: Optional[str]) -> Optional[str]:
    if not session_id:
        return None
    with _LOCK:
        return _read().get(session_id)


def destroy_session(session_id: Optional[str]) -> None:
    if not session_id:
        return
    with _LOCK:
        sessions = _read()
        if sessions.pop(session_id, None) is not None:
            _write(sessions)
