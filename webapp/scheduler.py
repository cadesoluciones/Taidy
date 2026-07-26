# -*- coding: utf-8 -*-
"""
Background scheduling for Taidy's webapp.

Schedule *definitions* are persisted as JSON next to this file so they
survive app restarts. The actual timers live in an APScheduler
BackgroundScheduler built once per process in FastAPI's lifespan hook (see
api/main.py) and kept running regardless of which page the browser is
showing.

When a trigger fires, this module hands off to webapp/tasks.launch(), the
exact same entry point manual "Run" buttons use — so a scheduled run shows
up on the "Tareas en curso" page and can be stopped just like a manual one.
Run *history* (what actually happened) lives in webapp/history.py, recorded
automatically by tasks.py when each run finishes, not here.

Caveat that must stay visible to whoever deploys this: jobs only fire while
this process is alive. On the target Linux deployment, run the app under a
process supervisor (systemd, Docker with a restart policy, etc.) so it keeps
running unattended instead of only while a terminal is open.
"""

from __future__ import annotations

import json
import sys
import threading
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import List, Optional

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from webapp import history, tasks, workflow_engine  # noqa: E402
from webapp.state_dir import state_path  # noqa: E402

_SCHEDULES_PATH = state_path("schedules.json", Path(__file__).resolve().parent)
_STORE_LOCK = threading.Lock()

# Actions whose stored `end_on` would go stale for a recurring job; recomputed
# as "today" at execution time instead of trusting whatever was saved.
_RECOMPUTE_END_ON = {"extract_factorial", "sync_factorial"}


# --------------------------------------------------------------------------------------
# JSON persistence helpers
# --------------------------------------------------------------------------------------


def _read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, data) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def list_schedules() -> List[dict]:
    with _STORE_LOCK:
        return _read_json(_SCHEDULES_PATH, [])


def _find_schedule(schedule_id: str) -> Optional[dict]:
    return next((s for s in list_schedules() if s["id"] == schedule_id), None)


# --------------------------------------------------------------------------------------
# Trigger construction
# --------------------------------------------------------------------------------------


def _build_trigger(trigger: str, trigger_args: dict):
    if trigger == "interval":
        return IntervalTrigger(**trigger_args)
    if trigger == "cron":
        return CronTrigger.from_crontab(trigger_args["expr"])
    raise ValueError(f"Tipo de trigger desconocido: {trigger}")


# --------------------------------------------------------------------------------------
# Schedule CRUD (persists to JSON, then mirrors into the live scheduler)
# --------------------------------------------------------------------------------------


def add_schedule(
    scheduler: BackgroundScheduler,
    *,
    name: str,
    action: str,
    params: dict,
    trigger: str,
    trigger_args: dict,
) -> dict:
    if action not in tasks.ACTION_LABELS and action != "run_workflow":
        raise ValueError(f"Acción desconocida: {action}")
    apscheduler_trigger = _build_trigger(trigger, trigger_args)  # raises early if invalid

    schedule = {
        "id": uuid.uuid4().hex,
        "name": name,
        "action": action,
        "params": params,
        "trigger": trigger,
        "trigger_args": trigger_args,
        "enabled": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with _STORE_LOCK:
        schedules = _read_json(_SCHEDULES_PATH, [])
        schedules.append(schedule)
        _write_json(_SCHEDULES_PATH, schedules)

    scheduler.add_job(
        _run_scheduled,
        trigger=apscheduler_trigger,
        args=[schedule["id"]],
        id=schedule["id"],
        replace_existing=True,
        misfire_grace_time=3600,
        coalesce=True,
        max_instances=1,
    )
    return schedule


def remove_schedule(scheduler: BackgroundScheduler, schedule_id: str) -> None:
    with _STORE_LOCK:
        schedules = _read_json(_SCHEDULES_PATH, [])
        schedules = [s for s in schedules if s["id"] != schedule_id]
        _write_json(_SCHEDULES_PATH, schedules)
    try:
        scheduler.remove_job(schedule_id)
    except JobLookupError:
        pass


def set_schedule_enabled(scheduler: BackgroundScheduler, schedule_id: str, enabled: bool) -> None:
    with _STORE_LOCK:
        schedules = _read_json(_SCHEDULES_PATH, [])
        for s in schedules:
            if s["id"] == schedule_id:
                s["enabled"] = enabled
        _write_json(_SCHEDULES_PATH, schedules)

    if enabled:
        schedule = _find_schedule(schedule_id)
        if schedule:
            apscheduler_trigger = _build_trigger(schedule["trigger"], schedule["trigger_args"])
            scheduler.add_job(
                _run_scheduled,
                trigger=apscheduler_trigger,
                args=[schedule_id],
                id=schedule_id,
                replace_existing=True,
                misfire_grace_time=3600,
                coalesce=True,
                max_instances=1,
            )
    else:
        try:
            scheduler.remove_job(schedule_id)
        except JobLookupError:
            pass


def _run_scheduled(schedule_id: str) -> None:
    schedule = _find_schedule(schedule_id)
    if schedule is None or not schedule.get("enabled", True):
        return

    action = schedule["action"]
    params = dict(schedule.get("params") or {})
    if action in _RECOMPUTE_END_ON:
        params["end_on"] = date.today().isoformat()

    triggered_by = f"programada: {schedule.get('name', schedule_id)}"
    try:
        if action == "run_workflow":
            workflow_engine.start_workflow(params["workflow_id"], triggered_by, notify=bool(params.get("notify", False)))
        else:
            tasks.launch(action, params, triggered_by)
    except Exception as exc:
        # launch() failed before a Task even existed (bad action, or a
        # conflicting task already running) — record it directly.
        history.record_run(
            action=action,
            source=triggered_by,
            status="error",
            ok=False,
            message=f"No se pudo iniciar: {exc}",
            log="",
        )


# --------------------------------------------------------------------------------------
# Scheduler bootstrap
# --------------------------------------------------------------------------------------


def build_scheduler() -> BackgroundScheduler:
    """Creates the BackgroundScheduler and re-registers all persisted schedules.

    Call this exactly once per process (from api/main.py's lifespan startup)
    so restarting the app re-loads schedules.json instead of losing every
    schedule.
    """
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.start()

    for schedule in list_schedules():
        if not schedule.get("enabled", True):
            continue
        try:
            apscheduler_trigger = _build_trigger(schedule["trigger"], schedule["trigger_args"])
        except Exception:
            continue  # malformed entry from an old version — skip rather than crash startup
        scheduler.add_job(
            _run_scheduled,
            trigger=apscheduler_trigger,
            args=[schedule["id"]],
            id=schedule["id"],
            replace_existing=True,
            misfire_grace_time=3600,
            coalesce=True,
            max_instances=1,
        )
    return scheduler
