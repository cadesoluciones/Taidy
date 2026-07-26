# -*- coding: utf-8 -*-
"""GET /dashboard/summary -- backs the React "Inicio" page (F-05).

GET /dashboard/mine-workflows backs the same page's Reader-facing view: per
workflow the caller can access (see webapp/workflows.list_workflows_for_user),
its current run (if any), its most recent finished run, and whether any
enabled schedule targets it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from webapp import history, scheduler as sched_module, tasks, workflow_engine, workflows as workflows_module

from ..dependencies import CurrentUser, get_current_user
from ..schemas.dashboard import DashboardSummaryOut, MyWorkflowsOut, MyWorkflowStatusOut, RecentRunOut
from .workflows import run_to_out

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummaryOut, dependencies=[Depends(get_current_user)])
def summary() -> DashboardSummaryOut:
    running_tasks = [t for t in tasks.list_tasks() if t.status == "running"]
    running_workflows = [r for r in workflow_engine.list_runs() if r.status == "running"]
    active_schedules = [s for s in sched_module.list_schedules() if s.get("enabled", True)]
    recent = history.get_history(limit=5)
    recent_errors = sum(1 for e in recent if not e["ok"] and e.get("status") != "stopped")

    return DashboardSummaryOut(
        running_count=len(running_tasks) + len(running_workflows),
        active_schedule_count=len(active_schedules),
        recent_error_count=recent_errors,
        recent_history=[
            RecentRunOut(
                action=e["action"],
                source=e["source"],
                ok=e["ok"],
                status=e.get("status", ""),
                finished_at=e["finished_at"],
                message=e["message"],
            )
            for e in recent
        ],
    )


@router.get("/mine-workflows", response_model=MyWorkflowsOut, dependencies=[Depends(get_current_user)])
def mine_workflows(current: CurrentUser = Depends(get_current_user)) -> MyWorkflowsOut:
    accessible = workflows_module.list_workflows_for_user(current.username, current.role)
    runs = workflow_engine.list_runs()  # newest first, see workflow_engine.list_runs()
    schedules = sched_module.list_schedules()

    items = []
    for wf in accessible:
        wf_runs = [r for r in runs if r.workflow_id == wf["id"]]
        current_run = next((r for r in wf_runs if r.status == "running"), None)
        last_run = next((r for r in wf_runs if r.status != "running"), None)
        scheduled = any(
            s.get("enabled", True)
            and s.get("action") == "run_workflow"
            and s.get("params", {}).get("workflow_id") == wf["id"]
            for s in schedules
        )
        items.append(
            MyWorkflowStatusOut(
                id=wf["id"],
                name=wf["name"],
                current_run=run_to_out(current_run) if current_run else None,
                last_run=run_to_out(last_run) if last_run else None,
                scheduled=scheduled,
            )
        )
    return MyWorkflowsOut(items=items)
