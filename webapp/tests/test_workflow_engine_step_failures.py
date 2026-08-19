# -*- coding: utf-8 -*-
"""
_run_worker()'s handling of a step whose tasks.launch() call fails.

Regression coverage for a real production bug: a workflow step for
extract_factorial/sync_factorial never got its `end_on` recomputed (unlike
webapp/scheduler.py's equivalent scheduled-run path), so tasks.launch() kept
raising ValueError("'Desde' y 'Hasta' son obligatorios...") on every poll
tick forever -- caught by the (at the time) blanket `except (RuntimeError,
ValueError): continue`, which silently retried the same failure indefinitely
instead of ever finishing the run. The block sat on "pending" forever with
no visible error, and workflow_already_running() kept blocking every
relaunch attempt.
"""

from __future__ import annotations

import time

from webapp import workflow_engine, workflows


def _wait_until_run_finished(run_id: str, timeout: float = 10.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = workflow_engine.get_run(run_id)
        if run is not None and run.status != "running":
            return
        time.sleep(0.05)


def test_factorial_step_gets_end_on_recomputed_so_it_actually_runs(isolated_state, fake_subprocess):
    workflow = workflows.create_workflow(
        "Flujo Factorial",
        [
            {
                "id": "s1",
                "label": "Sync Factorial",
                "action": "sync_factorial",
                # No end_on saved -- neither the workflow editor nor Tareas
                # programadas ever collect it; "Hasta" is always "today".
                "params": {"start_on": "2025-01-01", "employee_status": "active"},
                "depends_on": [],
            }
        ],
    )
    run = workflow_engine.start_workflow(workflow["id"], "admin")

    _wait_until_run_finished(run.id, timeout=10.0)

    assert run.status == "ok"
    assert run.steps["s1"].status == "ok"


def test_step_with_permanently_invalid_params_fails_instead_of_retrying_forever(isolated_state, fake_subprocess):
    workflow = workflows.create_workflow(
        "Flujo mal configurado",
        [
            {
                "id": "s1",
                "label": "Pipeline sin elegir",
                # Missing "pipeline" -- tasks.launch() raises ValueError for
                # this every single time, which used to loop forever.
                "action": "run_pipeline",
                "params": {},
                "depends_on": [],
            },
            {
                "id": "s2",
                "label": "Depende del anterior",
                "action": "upload_bc",
                "params": {},
                "depends_on": ["s1"],
            },
        ],
    )
    run = workflow_engine.start_workflow(workflow["id"], "admin")

    _wait_until_run_finished(run.id, timeout=10.0)

    assert run.status == "error"
    assert run.steps["s1"].status == "error"
    assert "pipeline" in (run.steps["s1"].detail or "").lower()
    # Cascade-cancelled, same as a step whose dependency failed for any other reason.
    assert run.steps["s2"].status == "cancelled"
