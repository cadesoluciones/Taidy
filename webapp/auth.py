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

users_db.init_db()


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
        with _AUDIT_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def get_audit_log(limit: int = 200) -> List[dict]:
    if not _AUDIT_LOG_PATH.exists():
        return []
    lines = _AUDIT_LOG_PATH.read_text(encoding="utf-8").splitlines()
    entries = []
    for line in lines[-limit:]:
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return list(reversed(entries))
