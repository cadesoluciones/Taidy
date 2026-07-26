# -*- coding: utf-8 -*-
"""
A recurring Factorial extract/sync schedule must never trust the `end_on`
saved into schedules.json at creation time -- for a job that fires nightly,
"Hasta" has to be TODAY every time it runs, not whichever day the schedule
happened to be created on. webapp/scheduler.py:_RECOMPUTE_END_ON already
encodes this (recomputing `end_on` fresh at execution time); these tests
prove it, so a future refactor of _run_scheduled() can't silently drop it.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from webapp import scheduler as sched_module, tasks


def _capture_launch(monkeypatch):
    captured = {}

    def _fake_launch(action, params, triggered_by):
        captured["action"] = action
        captured["params"] = dict(params)
        captured["triggered_by"] = triggered_by

        class _FakeTask:
            id = "fake-task-id"

        return _FakeTask()

    monkeypatch.setattr(tasks, "launch", _fake_launch)
    return captured


def _write_schedule(action: str, params: dict) -> str:
    schedule = {
        "id": "sched-under-test",
        "name": "Nightly job",
        "action": action,
        "params": params,
        "trigger": "interval",
        "trigger_args": {"hours": 24},
        "enabled": True,
        "created_at": "2025-01-01T00:00:00+00:00",
    }
    sched_module._write_json(sched_module._SCHEDULES_PATH, [schedule])
    return schedule["id"]


def test_scheduled_extract_factorial_recomputes_end_on_to_today(isolated_state, monkeypatch):
    stale_end_on = (date.today() - timedelta(days=30)).isoformat()
    schedule_id = _write_schedule(
        "extract_factorial",
        {"start_on": "2025-01-01", "end_on": stale_end_on, "employee_status": "active"},
    )
    captured = _capture_launch(monkeypatch)

    sched_module._run_scheduled(schedule_id)

    assert captured["action"] == "extract_factorial"
    assert captured["params"]["end_on"] == date.today().isoformat()
    assert captured["params"]["end_on"] != stale_end_on
    assert captured["params"]["start_on"] == "2025-01-01"  # untouched


def test_scheduled_sync_factorial_recomputes_end_on_to_today(isolated_state, monkeypatch):
    stale_end_on = "2020-01-01"
    schedule_id = _write_schedule("sync_factorial", {"start_on": "2025-01-01", "end_on": stale_end_on})
    captured = _capture_launch(monkeypatch)

    sched_module._run_scheduled(schedule_id)

    assert captured["params"]["end_on"] == date.today().isoformat()


def test_scheduled_extract_factorial_gets_end_on_even_if_never_saved(isolated_state, monkeypatch):
    """A schedule created before end_on was ever collected (or one saved
    without it) must still get today's date at execution time -- the
    recompute must ADD the key, not just overwrite an existing one."""
    schedule_id = _write_schedule("extract_factorial", {"start_on": "2025-01-01"})
    captured = _capture_launch(monkeypatch)

    sched_module._run_scheduled(schedule_id)

    assert captured["params"]["end_on"] == date.today().isoformat()


def test_scheduled_extract_bc_is_not_given_an_end_on(isolated_state, monkeypatch):
    schedule_id = _write_schedule("extract_bc", {"mode": "incremental", "parallel": 1})
    captured = _capture_launch(monkeypatch)

    sched_module._run_scheduled(schedule_id)

    assert "end_on" not in captured["params"]


# --------------------------------------------------------------------------------------
# Missed-schedule detection: build_scheduler() re-registers jobs from
# schedules.json on every restart, so a job that was due while the process
# was down leaves no trace in APScheduler itself (it never existed then).
# next_run_time is snapshotted to schedules.json specifically so a later
# restart can tell "due in the past" apart from "just hasn't fired yet".
# --------------------------------------------------------------------------------------


def test_schedule_missed_while_down_is_flagged_on_restart(isolated_state):
    scheduler = sched_module.build_scheduler()
    try:
        schedule = sched_module.add_schedule(
            scheduler,
            name="Nightly",
            action="extract_bc",
            params={"mode": "incremental", "parallel": 1},
            trigger="interval",
            trigger_args={"hours": 24},
        )
    finally:
        scheduler.shutdown(wait=False)

    # Simulate the process having been down past the fire time: back-date the
    # saved next_run_time well beyond the misfire grace window (1h).
    overdue = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    sched_module._update_schedule_fields(schedule["id"], next_run_time=overdue)

    scheduler2 = sched_module.build_scheduler()
    try:
        reloaded = sched_module._find_schedule(schedule["id"])
    finally:
        scheduler2.shutdown(wait=False)

    assert reloaded["missed_last_run"] is True


def test_schedule_not_flagged_when_next_run_time_is_still_ahead(isolated_state):
    scheduler = sched_module.build_scheduler()
    try:
        schedule = sched_module.add_schedule(
            scheduler,
            name="Nightly",
            action="extract_bc",
            params={"mode": "incremental", "parallel": 1},
            trigger="interval",
            trigger_args={"hours": 24},
        )
    finally:
        scheduler.shutdown(wait=False)

    scheduler2 = sched_module.build_scheduler()
    try:
        reloaded = sched_module._find_schedule(schedule["id"])
    finally:
        scheduler2.shutdown(wait=False)

    assert reloaded["missed_last_run"] is False
    assert reloaded["next_run_time"] is not None


def test_running_a_missed_schedule_clears_the_missed_flag(isolated_state, monkeypatch):
    _capture_launch(monkeypatch)
    schedule_id = _write_schedule("extract_bc", {"mode": "incremental", "parallel": 1})
    sched_module._update_schedule_fields(schedule_id, missed_last_run=True)

    sched_module._run_scheduled(schedule_id)

    assert sched_module._find_schedule(schedule_id)["missed_last_run"] is False


def test_disabling_a_schedule_clears_next_run_time_and_missed_flag(isolated_state):
    scheduler = sched_module.build_scheduler()
    try:
        schedule = sched_module.add_schedule(
            scheduler,
            name="Nightly",
            action="extract_bc",
            params={"mode": "incremental", "parallel": 1},
            trigger="interval",
            trigger_args={"hours": 24},
        )
        sched_module._update_schedule_fields(schedule["id"], missed_last_run=True)

        sched_module.set_schedule_enabled(scheduler, schedule["id"], False)
    finally:
        scheduler.shutdown(wait=False)

    reloaded = sched_module._find_schedule(schedule["id"])
    assert reloaded["next_run_time"] is None
    assert reloaded["missed_last_run"] is False
