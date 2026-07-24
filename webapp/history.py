# -*- coding: utf-8 -*-
"""
Persisted history of task runs (manual or scheduled), independent of both the
task engine (webapp/tasks.py) and the scheduler (webapp/scheduler.py) so
neither has to import the other through this.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

_HISTORY_PATH = Path(__file__).resolve().parent / "run_history.json"
_LOCK = threading.Lock()
_MAX_HISTORY = 200
_MAX_LOG_CHARS = 20_000


def _read() -> list:
    if not _HISTORY_PATH.exists():
        return []
    try:
        return json.loads(_HISTORY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def _write(data: list) -> None:
    tmp = _HISTORY_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(_HISTORY_PATH)


def record_run(
    *,
    action: str,
    source: str,
    status: str,
    ok: bool,
    message: str,
    log: str,
    duration_seconds: Optional[float] = None,
) -> None:
    entry = {
        "id": uuid.uuid4().hex,
        "action": action,
        "source": source,
        "status": status,
        "ok": ok,
        "message": message,
        "duration_seconds": round(duration_seconds, 1) if duration_seconds is not None else None,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "log": log[-_MAX_LOG_CHARS:],
    }
    with _LOCK:
        data = _read()
        data.append(entry)
        data = data[-_MAX_HISTORY:]
        _write(data)


def get_history(limit: int = 50) -> List[dict]:
    with _LOCK:
        data = _read()
    return list(reversed(data[-limit:]))
