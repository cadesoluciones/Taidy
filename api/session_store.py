# -*- coding: utf-8 -*-
"""
Persisted session store for the FastAPI cookie session (session_id ->
{username, created_at}).

Plain JSON file, read fresh and written through on every call -- the same
"file is the single source of truth, no in-memory cache" pattern
webapp/scheduler.py/workflows.py/history.py already use, so a restart no
longer logs out every signed-in user (the previous in-memory-only dict did).
Kept out of webapp/ since sessions are a FastAPI-only concept.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from webapp.state_dir import state_path

_SESSIONS_PATH = state_path("sessions.json", Path(__file__).resolve().parent)
_LOCK = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize(raw: dict) -> Dict[str, dict]:
    """Sessions created before "sesiones activas" was added were stored as a
    plain `session_id -> username` string; upgrade those in place instead of
    silently logging everyone out on the first read after deploying this."""
    normalized: Dict[str, dict] = {}
    for session_id, value in raw.items():
        if isinstance(value, str):
            normalized[session_id] = {"username": value, "created_at": _now_iso()}
        elif isinstance(value, dict) and isinstance(value.get("username"), str):
            normalized[session_id] = value
    return normalized


def _read() -> Dict[str, dict]:
    if not _SESSIONS_PATH.is_file():
        return {}
    try:
        data = json.loads(_SESSIONS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return _normalize(data) if isinstance(data, dict) else {}


def _write(sessions: Dict[str, dict]) -> None:
    tmp = _SESSIONS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(sessions), encoding="utf-8")
    tmp.replace(_SESSIONS_PATH)


def _session_ref(session_id: str) -> str:
    """A short, stable, non-reversible reference so an admin UI can list and
    revoke a specific session without ever exposing the real session_id --
    that value IS the bearer credential; leaking it would let someone
    hijack the session directly by setting that cookie themselves."""
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:12]


def create_session(username: str) -> str:
    session_id = secrets.token_urlsafe(32)
    with _LOCK:
        sessions = _read()
        sessions[session_id] = {"username": username, "created_at": _now_iso()}
        _write(sessions)
    return session_id


def get_session_username(session_id: Optional[str]) -> Optional[str]:
    # A pure read, deliberately -- this runs on every single authenticated
    # request (get_current_user_allow_pending depends on it). Writing a
    # "last seen" timestamp here would turn every request into a locked
    # file read+write, serializing all concurrent requests through one
    # lock; "sesiones activas" only needs to show when a session started,
    # not second-by-second recency.
    if not session_id:
        return None
    with _LOCK:
        record = _read().get(session_id)
    return record["username"] if record else None


def destroy_session(session_id: Optional[str]) -> None:
    if not session_id:
        return
    with _LOCK:
        sessions = _read()
        if sessions.pop(session_id, None) is not None:
            _write(sessions)


def list_sessions_for_user(username: str) -> List[dict]:
    """Newest-first. Never includes the real session_id -- see _session_ref."""
    with _LOCK:
        sessions = _read()
    matching = [
        {"session_ref": _session_ref(sid), "created_at": r["created_at"]}
        for sid, r in sessions.items()
        if r["username"] == username
    ]
    return sorted(matching, key=lambda r: r["created_at"], reverse=True)


def revoke_session_by_ref(username: str, session_ref: str) -> bool:
    """Revokes one of `username`'s own sessions identified by its ref --
    scoped to that username so a ref can never be used to reach into another
    user's sessions (SHA-256-truncated collisions are practically impossible
    anyway, but this costs nothing and removes the question entirely)."""
    with _LOCK:
        sessions = _read()
        target_id = next(
            (sid for sid, r in sessions.items() if r["username"] == username and _session_ref(sid) == session_ref),
            None,
        )
        if target_id is None:
            return False
        del sessions[target_id]
        _write(sessions)
        return True
