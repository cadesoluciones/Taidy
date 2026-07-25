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

from datetime import date, timedelta

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
