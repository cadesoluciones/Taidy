# -*- coding: utf-8 -*-
"""
Continuity between a workflow run and its steps, in two places a user
actually looks at them:

1. Historial -- each step's task-level history entry, and the run's own
   summary entry, now share a real `workflow_run_id`/`workflow_name` instead
   of only a free-text "flujo: X / paso: Y" string in `source` (which can't
   even tell two different runs of the same workflow apart).
2. The live/recent run view -- each StepRun now records started_at/
   finished_at, so the diagram can show elapsed time instead of just a
   status color.
"""

from __future__ import annotations

import time

from webapp import history, workflow_engine, workflows


def _wait_until_run_finished(run_id: str, timeout: float = 10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = workflow_engine.get_run(run_id)
        if run is not None and run.status != "running":
            return run
        time.sleep(0.05)
    raise AssertionError("run did not finish in time")


def _wait_until_history_has_run(run_id: str, expected_count: int, timeout: float = 10.0) -> list:
    """run.status flips to a terminal value INSIDE _finalize(), a few lines
    before it calls history.record_run() -- polling only on run.status (as
    _wait_until_run_finished does) can observe "finished" a hair before the
    matching history entries actually exist. Closes that race explicitly
    instead of letting a flaky assertion (or a write to the real, unpatched
    history file after this test's monkeypatch tears down) slip through."""
    deadline = time.time() + timeout
    matching: list = []
    while time.time() < deadline:
        matching = [e for e in history.get_history(limit=50) if e.get("workflow_run_id") == run_id]
        if len(matching) >= expected_count:
            return matching
        time.sleep(0.05)
    raise AssertionError(f"expected {expected_count} history entries for run {run_id}, found {len(matching)}")


def test_step_tasks_and_the_run_summary_share_the_same_workflow_run_id(isolated_state, fake_subprocess):
    workflow = workflows.create_workflow(
        "Flujo con continuidad",
        [
            {"id": "a", "label": "Bloque A", "action": "extract_bc", "params": {}, "depends_on": []},
            {"id": "b", "label": "Bloque B", "action": "upload_bc", "params": {}, "depends_on": ["a"]},
        ],
    )
    run = workflow_engine.start_workflow(workflow["id"], "admin")
    _wait_until_run_finished(run.id)
    entries = _wait_until_history_has_run(run.id, expected_count=3)

    step_entries = [e for e in entries if e["action"] != "run_workflow"]
    summary_entries = [e for e in entries if e["action"] == "run_workflow"]

    assert len(step_entries) == 2
    assert len(summary_entries) == 1
    assert all(e["workflow_name"] == "Flujo con continuidad" for e in step_entries + summary_entries)


def test_unrelated_manual_task_has_no_workflow_run_id(isolated_state, fake_subprocess):
    from webapp import tasks

    task = tasks.launch("upload_bc", {}, "admin")
    deadline = time.time() + 10
    entry = None
    while time.time() < deadline:
        entry = next((e for e in history.get_history(limit=5) if e["action"] == "upload_bc"), None)
        if entry is not None:
            break
        time.sleep(0.05)
    assert entry is not None, "upload_bc never showed up in history in time"
    assert entry["workflow_run_id"] is None
    assert entry["workflow_name"] is None


def test_two_separate_runs_of_the_same_workflow_get_distinct_run_ids(isolated_state, fake_subprocess):
    workflow = workflows.create_workflow(
        "Flujo repetido",
        [{"id": "a", "label": "Bloque A", "action": "upload_bc", "params": {}, "depends_on": []}],
    )
    run1 = workflow_engine.start_workflow(workflow["id"], "admin")
    _wait_until_run_finished(run1.id)
    _wait_until_history_has_run(run1.id, expected_count=2)
    run2 = workflow_engine.start_workflow(workflow["id"], "admin")
    _wait_until_run_finished(run2.id)
    _wait_until_history_has_run(run2.id, expected_count=2)

    assert run1.id != run2.id
    entries = history.get_history(limit=10)
    run_ids_seen = {e["workflow_run_id"] for e in entries if e.get("workflow_name") == "Flujo repetido"}
    assert run_ids_seen == {run1.id, run2.id}


def test_step_run_records_started_and_finished_timestamps(isolated_state, fake_subprocess):
    workflow = workflows.create_workflow(
        "Flujo con tiempos",
        [{"id": "a", "label": "Bloque A", "action": "upload_bc", "params": {}, "depends_on": []}],
    )
    run = workflow_engine.start_workflow(workflow["id"], "admin")
    finished_run = _wait_until_run_finished(run.id)
    # Not asserted on below, but waiting for it closes the race between this
    # test returning (monkeypatch tearing down _HISTORY_PATH) and the
    # background worker thread's _finalize() still mid-flight -- see
    # _wait_until_history_has_run's docstring.
    _wait_until_history_has_run(run.id, expected_count=2)

    step = finished_run.steps["a"]
    assert step.started_at is not None
    assert step.finished_at is not None
    assert step.started_at <= step.finished_at


def test_cancelled_step_has_no_started_at_but_has_finished_at(isolated_state, monkeypatch):
    """A step cascade-cancelled because its dependency failed never actually
    launches a task -- it should never claim a start time, but should still
    record when it was resolved (cancelled)."""
    import subprocess
    import sys

    from webapp import tasks

    def _fake_failing_popen(module: str, argv: list) -> subprocess.Popen:
        return subprocess.Popen(
            [sys.executable, "-c", "import sys; sys.exit(1)"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

    monkeypatch.setattr(tasks, "_popen", _fake_failing_popen)

    workflow = workflows.create_workflow(
        "Flujo con cancelado",
        [
            {"id": "a", "label": "Bloque A", "action": "upload_bc", "params": {}, "depends_on": []},
            {"id": "b", "label": "Bloque B", "action": "upload_bc", "params": {}, "depends_on": ["a"]},
        ],
    )
    run = workflow_engine.start_workflow(workflow["id"], "admin")
    finished_run = _wait_until_run_finished(run.id)
    # Only "a" (which actually launched a task) and the run's own summary
    # get a history entry -- "b" cascade-cancels without ever calling
    # tasks.launch(). Waiting for both closes the same teardown race as
    # above even though this test doesn't assert on history content.
    _wait_until_history_has_run(run.id, expected_count=2)

    assert finished_run.steps["a"].status == "error"
    assert finished_run.steps["b"].status == "cancelled"
    assert finished_run.steps["b"].started_at is None
    assert finished_run.steps["b"].finished_at is not None
