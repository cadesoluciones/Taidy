# -*- coding: utf-8 -*-
"""
Background scheduling for NEXUS-BDB's webapp.

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
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from apscheduler.events import EVENT_JOB_EXECUTED
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

# How long APScheduler waits past a job's due time before giving up on that
# fire (also passed as misfire_grace_time below). Used again at startup to
# decide whether a next_run_time saved before a restart is now far enough in
# the past that the fire it represented was genuinely missed, not just late.
_MISFIRE_GRACE_SECONDS = 3600


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


def _update_schedule_fields(schedule_id: str, **fields) -> None:
    with _STORE_LOCK:
        schedules = _read_json(_SCHEDULES_PATH, [])
        changed = False
        for s in schedules:
            if s["id"] == schedule_id:
                s.update(fields)
                changed = True
        if changed:
            _write_json(_SCHEDULES_PATH, schedules)


def _snapshot_next_run_time(scheduler: BackgroundScheduler, schedule_id: str) -> None:
    """Persists APScheduler's live next_run_time so it survives a restart --
    it's the only way to later tell whether a fire was missed while the
    process was down (see build_scheduler's startup check)."""
    job = scheduler.get_job(schedule_id)
    next_run = job.next_run_time.isoformat() if job and job.next_run_time else None
    _update_schedule_fields(schedule_id, next_run_time=next_run)


# --------------------------------------------------------------------------------------
# Trigger construction
# --------------------------------------------------------------------------------------


def _build_trigger(trigger: str, trigger_args: dict):
    if trigger == "interval":
        return IntervalTrigger(**trigger_args)
    if trigger == "cron":
        return CronTrigger.from_crontab(trigger_args["expr"])
    raise ValueError(f"Tipo de trigger desconocido: {trigger}")


# Safety net for a pathological trigger (e.g. "every minute") that would
# otherwise flood a week view with thousands of occurrences.
_MAX_WEEK_OCCURRENCES_PER_SCHEDULE = 200


def _build_trigger_for_display(schedule: dict):
    """Like _build_trigger, but an interval schedule with no explicit
    start_date (the normal case -- the UI never sets one) gets anchored to
    when the schedule was actually created instead of "now".

    IntervalTrigger(**trigger_args) with no start_date defaults to
    datetime.now(local_tz) + interval -- correct for the *live* scheduler,
    where that trigger object is built exactly once (in add_schedule/
    build_scheduler) and kept in memory for the job's whole lifetime, so its
    anchor never moves again. week_occurrences() has no such live object to
    reuse and rebuilds the trigger from scratch on every call; without this,
    every call would silently re-anchor to whatever moment it happened to
    run at, making a schedule's week-view occurrences drift depending on
    when the calendar page happens to be loaded instead of reflecting when
    the schedule was actually created.
    """
    if schedule["trigger"] == "interval" and "start_date" not in schedule["trigger_args"]:
        args = dict(schedule["trigger_args"])
        args["start_date"] = datetime.fromisoformat(schedule["created_at"])
        return IntervalTrigger(**args)
    return _build_trigger(schedule["trigger"], schedule["trigger_args"])


def week_occurrences(reference: Optional[datetime] = None) -> Dict[str, List[str]]:
    """schedule_id -> ISO datetimes this schedule is due to fire within the
    current week (Monday 00:00 through the following Sunday 23:59:59, UTC),
    computed via the exact same trigger objects the live scheduler uses
    (IntervalTrigger/CronTrigger.get_next_fire_time) -- not a reimplemented
    cron/interval calculation that could silently drift from what actually
    fires.
    """
    now = reference or datetime.now(timezone.utc)
    week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    week_end = week_start + timedelta(days=7)

    result: Dict[str, List[str]] = {}
    for schedule in list_schedules():
        if not schedule.get("enabled", True):
            continue
        try:
            trigger = _build_trigger_for_display(schedule)
        except Exception:
            continue

        occurrences: List[str] = []
        fire = trigger.get_next_fire_time(None, week_start)
        while fire is not None and fire < week_end and len(occurrences) < _MAX_WEEK_OCCURRENCES_PER_SCHEDULE:
            occurrences.append(fire.isoformat())
            fire = trigger.get_next_fire_time(fire, fire)
        result[schedule["id"]] = occurrences
    return result


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
        "next_run_time": None,
        "missed_last_run": False,
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
        misfire_grace_time=_MISFIRE_GRACE_SECONDS,
        coalesce=True,
        max_instances=1,
    )
    _snapshot_next_run_time(scheduler, schedule["id"])
    # _snapshot_next_run_time updated the persisted copy, not this local dict --
    # re-read so the caller (and the API response) reflects next_run_time too.
    return _find_schedule(schedule["id"])


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
                misfire_grace_time=_MISFIRE_GRACE_SECONDS,
                coalesce=True,
                max_instances=1,
            )
            _snapshot_next_run_time(scheduler, schedule_id)
    else:
        try:
            scheduler.remove_job(schedule_id)
        except JobLookupError:
            pass
        _update_schedule_fields(schedule_id, next_run_time=None, missed_last_run=False)


def _run_scheduled(schedule_id: str) -> None:
    schedule = _find_schedule(schedule_id)
    if schedule is None or not schedule.get("enabled", True):
        return

    if schedule.get("missed_last_run"):
        _update_schedule_fields(schedule_id, missed_last_run=False)

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

    def _on_job_executed(event) -> None:
        # Recurring triggers get a new next_run_time as soon as they fire;
        # re-snapshot it so a later restart's missed-run check compares
        # against an up-to-date value instead of the one from before this run.
        _snapshot_next_run_time(scheduler, event.job_id)

    scheduler.add_listener(_on_job_executed, EVENT_JOB_EXECUTED)

    for schedule in list_schedules():
        if not schedule.get("enabled", True):
            continue
        try:
            apscheduler_trigger = _build_trigger(schedule["trigger"], schedule["trigger_args"])
        except Exception:
            continue  # malformed entry from an old version — skip rather than crash startup

        # The scheduler (and this in-memory job) didn't exist while the
        # process was down, so APScheduler itself never saw whatever fire
        # was due in that window -- it can't self-report a missed run here.
        # The only trace of it is the next_run_time we saved before shutdown.
        stored_next_run = schedule.get("next_run_time")
        if stored_next_run:
            try:
                due_at = datetime.fromisoformat(stored_next_run)
                if datetime.now(timezone.utc) > due_at + timedelta(seconds=_MISFIRE_GRACE_SECONDS):
                    _update_schedule_fields(schedule["id"], missed_last_run=True)
            except ValueError:
                pass

        scheduler.add_job(
            _run_scheduled,
            trigger=apscheduler_trigger,
            args=[schedule["id"]],
            id=schedule["id"],
            replace_existing=True,
            misfire_grace_time=_MISFIRE_GRACE_SECONDS,
            coalesce=True,
            max_instances=1,
        )
        _snapshot_next_run_time(scheduler, schedule["id"])
    return scheduler
