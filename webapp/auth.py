# -*- coding: utf-8 -*-
"""
Security-event audit log, shared by every UI that authenticates against
webapp/users_db.py (SQLite, bcrypt-hashed passwords, per-user lockout after
repeated failures).

Session/role enforcement itself lives in api/dependencies.py (FastAPI
dependency, re-checked server-side on every request) — this module only
owns the audit trail: one JSON line per auth-relevant event (login, logout,
access denied, password change). Never contains passwords or password
hashes.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from webapp import users_db
from webapp.state_dir import state_path

_AUDIT_LOG_PATH = state_path("audit.log", Path(__file__).resolve().parent)
_AUDIT_LOCK = threading.Lock()

# Bounds how large audit.log grows before rotating -- well beyond the 200-entry
# limit the UI ever requests (api/routers/audit.py), this only exists to stop
# an append-only, forever-running file from growing without limit. Rotated
# content is kept (as audit.log.1, .2, ...), not discarded: it's a security
# trail, so old entries move to backups instead of being deleted outright.
_MAX_AUDIT_LOG_BYTES = 2_000_000
_MAX_AUDIT_BACKUPS = 3

users_db.init_db()


def _rotate_audit_log_if_needed() -> None:
    """Call only while holding _AUDIT_LOCK. Shifts audit.log -> .1 -> .2 ...
    once the live file crosses _MAX_AUDIT_LOG_BYTES; the oldest backup beyond
    _MAX_AUDIT_BACKUPS is dropped."""
    try:
        if not _AUDIT_LOG_PATH.exists() or _AUDIT_LOG_PATH.stat().st_size < _MAX_AUDIT_LOG_BYTES:
            return
    except OSError:
        return
    for i in range(_MAX_AUDIT_BACKUPS - 1, 0, -1):
        src = _AUDIT_LOG_PATH.parent / f"{_AUDIT_LOG_PATH.name}.{i}"
        dst = _AUDIT_LOG_PATH.parent / f"{_AUDIT_LOG_PATH.name}.{i + 1}"
        if src.exists():
            src.replace(dst)
    _AUDIT_LOG_PATH.replace(_AUDIT_LOG_PATH.parent / f"{_AUDIT_LOG_PATH.name}.1")


def _audit(event: str, outcome: str, *, user: str = "-", detail: str = "") -> None:
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "outcome": outcome,
        "user": user,
        "detail": detail,
    }
    line = json.dumps(entry, ensure_ascii=False)
    with _AUDIT_LOCK:
        _rotate_audit_log_if_needed()
        with _AUDIT_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def get_audit_log(limit: int = 200) -> List[dict]:
    # Reads the live file first and only falls back to older backups when it
    # alone doesn't have `limit` entries yet -- right after a rotation. In the
    # common case this reads exactly one (size-bounded) file instead of the
    # unbounded, ever-growing single file the old implementation read in full
    # on every call.
    collected: List[str] = []
    candidate_paths = [_AUDIT_LOG_PATH] + [
        _AUDIT_LOG_PATH.parent / f"{_AUDIT_LOG_PATH.name}.{i}" for i in range(1, _MAX_AUDIT_BACKUPS + 1)
    ]
    for path in candidate_paths:
        if not path.exists():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        collected = lines + collected  # older file's lines come before newer ones
        if len(collected) >= limit:
            break

    entries = []
    for line in collected[-limit:]:
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return list(reversed(entries))
