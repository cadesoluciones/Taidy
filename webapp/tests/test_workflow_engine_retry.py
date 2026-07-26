# -*- coding: utf-8 -*-
"""
retry_failed_steps() validation paths: unknown run, wrong run status,
workflow already running elsewhere, and the workflow definition having
changed since the run started. None of these reach the point of starting a
worker thread, so they're safe to test without a real (fake) subprocess --
see api/tests/test_workflows.py for the happy-path test that actually lets
the retried step run to completion.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from webapp import workflow_engine, workflows
from webapp.workflow_engine import StepRun, WorkflowRun

_STEPS = [
    {"id": "a", "label": "Paso A", "action": "extract_bc", "params": {}, "depends_on": [], "trigger_rule": "all_success"},
    {
        "id": "b",
        "label": "Paso B",
        "action": "upload_factorial",
        "params": {},
        "depends_on": ["a"],
        "trigger_rule": "all_success",
    },
]


def _make_errored_run(workflow_id: str, workflow_name: str) -> WorkflowRun:
    """A finished run where step 'a' failed and 'b' got cascade-cancelled
    because its only dependency didn't succeed."""
    run = WorkflowRun(
        id=uuid.uuid4().hex,
        workflow_id=workflow_id,
        workflow_name=workflow_name,
        triggered_by="admin",
        started_at=datetime.now(timezone.utc).isoformat(),
        finished_at=datetime.now(timezone.utc).isoformat(),
        status="error",
        steps={
            "a": StepRun(
                id="a", label="Paso A", action="extract_bc", depends_on=[], trigger_rule="all_success",
                status="error", task_id="old-task-a",
            ),
            "b": StepRun(
                id="b", label="Paso B", action="upload_factorial", depends_on=["a"], trigger_rule="all_success",
                status="cancelled",
            ),
        },
    )
    workflow_engine._register(run)
    return run


def test_retry_unknown_run_raises_value_error(isolated_state):
    with pytest.raises(ValueError, match="desconocida"):
        workflow_engine.retry_failed_steps("does-not-exist", "operator1")


def test_retry_rejects_a_run_that_did_not_finish_with_error(isolated_state):
    workflow = workflows.create_workflow("Flujo 1", _STEPS)
    run = _make_errored_run(workflow["id"], workflow["name"])
    run.status = "stopped"  # a deliberate stop, not a failure -- not a retry candidate

    with pytest.raises(RuntimeError, match="error"):
        workflow_engine.retry_failed_steps(run.id, "operator1")


def test_retry_rejects_when_the_workflow_is_already_running_elsewhere(isolated_state):
    workflow = workflows.create_workflow("Flujo 1", _STEPS)
    run = _make_errored_run(workflow["id"], workflow["name"])

    other_run = WorkflowRun(
        id=uuid.uuid4().hex,
        workflow_id=workflow["id"],
        workflow_name=workflow["name"],
        triggered_by="admin",
        started_at=datetime.now(timezone.utc).isoformat(),
        status="running",
        steps={
            "a": StepRun(
                id="a", label="Paso A", action="extract_bc", depends_on=[], trigger_rule="all_success",
                status="running", task_id="t1",
            )
        },
    )
    workflow_engine._register(other_run)

    with pytest.raises(RuntimeError, match="ejecutando"):
        workflow_engine.retry_failed_steps(run.id, "operator1")


def test_retry_rejects_when_the_workflow_definition_no_longer_has_a_matching_step(isolated_state):
    workflow = workflows.create_workflow("Flujo 1", _STEPS)
    run = _make_errored_run(workflow["id"], workflow["name"])
    # The saved workflow changed (step "b" renamed/removed) since this run started.
    workflows.update_workflow(workflow["id"], workflow["name"], [_STEPS[0]])

    with pytest.raises(RuntimeError, match="modificado"):
        workflow_engine.retry_failed_steps(run.id, "operator1")


def test_retry_rejects_when_the_workflow_itself_was_deleted(isolated_state):
    workflow = workflows.create_workflow("Flujo 1", _STEPS)
    run = _make_errored_run(workflow["id"], workflow["name"])
    workflows.delete_workflow(workflow["id"])

    with pytest.raises(ValueError, match="ya no existe"):
        workflow_engine.retry_failed_steps(run.id, "operator1")
