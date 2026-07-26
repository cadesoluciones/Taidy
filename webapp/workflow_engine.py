# -*- coding: utf-8 -*-
"""
DAG orchestrator: runs a workflow's steps in dependency order, launching
independent steps in parallel via the same subprocess task engine
(webapp/tasks.py) already used for manual/scheduled single actions. Each
step becomes a normal Task, so it shows up (and can be stopped) exactly like
any other task in "Tareas en curso" — this module only decides *when* to
call tasks.launch() for each step, never executes anything itself.
"""

from __future__ import annotations

import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from webapp import history, notifications, tasks, workflows  # noqa: E402

_POLL_SECONDS = 2
_TERMINAL_TASK_STATUSES = {"ok", "error", "stopped"}
_TERMINAL_STEP_STATUSES = {"ok", "error", "cancelled", "stopped"}
_MAX_FINISHED_IN_MEMORY = 20


@dataclass
class StepRun:
    id: str
    label: str
    action: str
    depends_on: List[str]
    trigger_rule: str
    status: str = "pending"  # pending | running | ok | error | cancelled | stopped
    task_id: Optional[str] = None


@dataclass
class WorkflowRun:
    id: str
    workflow_id: str
    workflow_name: str
    triggered_by: str
    started_at: str
    steps: Dict[str, StepRun] = field(default_factory=dict)
    finished_at: Optional[str] = None
    status: str = "running"  # running | ok | error | stopped
    stop_requested: bool = False
    notify: bool = False
    retried: bool = False

    def step_status_map(self) -> Dict[str, str]:
        return {sid: s.status for sid, s in self.steps.items()}

    def duration_seconds(self) -> float:
        start = datetime.fromisoformat(self.started_at)
        end = datetime.fromisoformat(self.finished_at) if self.finished_at else datetime.now(timezone.utc)
        return (end - start).total_seconds()


_REGISTRY: Dict[str, WorkflowRun] = {}
_REGISTRY_LOCK = threading.Lock()


def list_runs() -> List[WorkflowRun]:
    with _REGISTRY_LOCK:
        runs = list(_REGISTRY.values())
    return sorted(runs, key=lambda r: r.started_at, reverse=True)


def get_run(run_id: str) -> Optional[WorkflowRun]:
    with _REGISTRY_LOCK:
        return _REGISTRY.get(run_id)


def _register(run: WorkflowRun) -> None:
    with _REGISTRY_LOCK:
        _REGISTRY[run.id] = run
        finished = sorted(
            (r for r in _REGISTRY.values() if r.status != "running"),
            key=lambda r: r.finished_at or "",
        )
        overflow = len(finished) - _MAX_FINISHED_IN_MEMORY
        for old in finished[: max(overflow, 0)]:
            _REGISTRY.pop(old.id, None)


def workflow_already_running(workflow_id: str) -> Optional[WorkflowRun]:
    with _REGISTRY_LOCK:
        for r in _REGISTRY.values():
            if r.workflow_id == workflow_id and r.status == "running":
                return r
    return None


def start_workflow(workflow_id: str, triggered_by: str, notify: bool = False) -> WorkflowRun:
    workflow = workflows.get_workflow(workflow_id)
    if workflow is None:
        raise ValueError(f"Flujo desconocido: {workflow_id}")

    blocker = workflow_already_running(workflow_id)
    if blocker is not None:
        raise RuntimeError(f"El flujo '{workflow['name']}' ya se está ejecutando. Espera a que termine.")

    step_defs = {s["id"]: s for s in workflow["steps"]}
    steps = {
        sid: StepRun(
            id=sid,
            label=sd.get("label") or sid,
            action=sd["action"],
            depends_on=list(sd.get("depends_on", [])),
            trigger_rule=sd.get("trigger_rule", workflows.TRIGGER_ALL_SUCCESS),
        )
        for sid, sd in step_defs.items()
    }
    run = WorkflowRun(
        id=uuid.uuid4().hex,
        workflow_id=workflow_id,
        workflow_name=workflow["name"],
        triggered_by=triggered_by,
        started_at=datetime.now(timezone.utc).isoformat(),
        steps=steps,
        notify=notify,
    )
    _register(run)

    threading.Thread(target=_run_worker, args=(run, step_defs), daemon=True, name=f"workflow-{run.id}").start()
    return run


def _run_worker(run: WorkflowRun, step_defs: Dict[str, dict]) -> None:
    while True:
        if run.stop_requested:
            _stop_running_and_cancel_pending(run)
            break

        if all(s.status in _TERMINAL_STEP_STATUSES for s in run.steps.values()):
            break

        # 1. Reflect the underlying tasks' current status onto running steps.
        for step in run.steps.values():
            if step.status == "running" and step.task_id:
                t = tasks.get_task(step.task_id)
                if t is not None and t.status in _TERMINAL_TASK_STATUSES:
                    step.status = t.status

        # 2. Launch steps whose dependencies are all resolved.
        for step in run.steps.values():
            if step.status != "pending":
                continue
            dep_states = [run.steps[d].status for d in step.depends_on]
            if not all(s in _TERMINAL_STEP_STATUSES for s in dep_states):
                continue  # still waiting on a predecessor

            if step.trigger_rule == workflows.TRIGGER_ALL_SUCCESS and any(s != "ok" for s in dep_states):
                step.status = "cancelled"
                continue

            try:
                task = tasks.launch(
                    step.action,
                    step_defs[step.id].get("params", {}),
                    f"flujo: {run.workflow_name} / paso: {step.label}",
                )
            except (RuntimeError, ValueError):
                # Usually a conflicting task elsewhere is still running — retry next tick.
                continue
            step.task_id = task.id
            step.status = "running"

        time.sleep(_POLL_SECONDS)

    _finalize(run)


def _stop_running_and_cancel_pending(run: WorkflowRun) -> None:
    for step in run.steps.values():
        if step.status == "running" and step.task_id:
            tasks.stop_task(step.task_id)
        elif step.status == "pending":
            step.status = "cancelled"

    # Give the stopped subprocesses a moment to actually report a terminal status.
    for _ in range(10):
        if all(s.status != "running" for s in run.steps.values()):
            break
        for step in run.steps.values():
            if step.status == "running" and step.task_id:
                t = tasks.get_task(step.task_id)
                if t is not None and t.status in _TERMINAL_TASK_STATUSES:
                    step.status = t.status
        time.sleep(0.5)


def _finalize(run: WorkflowRun) -> None:
    run.finished_at = datetime.now(timezone.utc).isoformat()
    statuses = {s.status for s in run.steps.values()}
    if run.stop_requested:
        run.status = "stopped"
    elif "error" in statuses:
        run.status = "error"
    else:
        run.status = "ok"

    ok_count = sum(1 for s in run.steps.values() if s.status == "ok")
    retried_suffix = " (reintento de los pasos fallidos)" if run.retried else ""
    message = f"Flujo '{run.workflow_name}': {ok_count}/{len(run.steps)} bloque(s) completados correctamente{retried_suffix}."
    history.record_run(
        action="run_workflow",
        source=run.triggered_by,
        status=run.status,
        ok=run.status == "ok",
        message=message,
        log="",
        duration_seconds=run.duration_seconds(),
    )
    if run.notify:
        notifications.notify_workflow_finished(
            workflow_name=run.workflow_name,
            triggered_by=run.triggered_by,
            status=run.status,
            message=message,
        )


def stop_workflow(run_id: str) -> bool:
    run = get_run(run_id)
    if run is None or run.status != "running":
        return False
    run.stop_requested = True
    return True


def retry_failed_steps(run_id: str, triggered_by: str) -> WorkflowRun:
    """Re-runs only the steps that failed (status "error") plus whatever got
    cascade-cancelled because of them, keeping every already-"ok" step's
    result as-is. Only valid for a run that finished with status "error" --
    a deliberately stopped run isn't a retry candidate.
    """
    run = get_run(run_id)
    if run is None:
        raise ValueError("Ejecución desconocida (puede haberse descartado ya de la memoria por ser antigua).")
    if run.status != "error":
        raise RuntimeError("Solo se puede reintentar una ejecución que haya terminado con error.")

    blocker = workflow_already_running(run.workflow_id)
    if blocker is not None:
        raise RuntimeError(f"El flujo '{run.workflow_name}' ya se está ejecutando. Espera a que termine.")

    workflow = workflows.get_workflow(run.workflow_id)
    if workflow is None:
        raise ValueError(f"El flujo original ya no existe: {run.workflow_id}")
    step_defs = {s["id"]: s for s in workflow["steps"]}
    if any(sid not in step_defs for sid in run.steps):
        raise RuntimeError("El flujo se ha modificado desde esta ejecución; no se puede reintentar de forma segura.")

    # "cancelled" steps only ever got that status because a dependency of
    # theirs wasn't "ok" (see the trigger_rule check in _run_worker) -- reset
    # them to pending too so they're re-evaluated once the retried step
    # they depended on resolves again, rather than staying stuck terminal.
    for step in run.steps.values():
        if step.status in ("error", "cancelled"):
            step.status = "pending"
            step.task_id = None

    run.status = "running"
    run.stop_requested = False
    run.finished_at = None
    run.retried = True
    run.triggered_by = triggered_by
    _register(run)

    threading.Thread(target=_run_worker, args=(run, step_defs), daemon=True, name=f"workflow-{run.id}-retry").start()
    return run
