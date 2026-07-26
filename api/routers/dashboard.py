# -*- coding: utf-8 -*-
"""GET /dashboard/summary -- backs the React "Inicio" page (F-05).

GET /dashboard/mine-workflows backs the same page's Reader-facing view: per
workflow the caller can access (see webapp/workflows.list_workflows_for_user),
its current run (if any), its most recent finished run, and whether any
enabled schedule targets it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from webapp import (
    alerts,
    history,
    llm_providers,
    scheduler as sched_module,
    summary as summary_module,
    tasks,
    workflow_engine,
    workflows as workflows_module,
)

from ..dependencies import CurrentUser, get_current_user
from ..schemas.dashboard import (
    DashboardSummaryOut,
    ErrorRateAlertOut,
    MyWorkflowsOut,
    MyWorkflowStatusOut,
    NarrativeSummaryOut,
    RecentRunOut,
)
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
        error_rate_alerts=[ErrorRateAlertOut(**a) for a in alerts.detect_elevated_error_rates()],
    )


@router.get("/narrative-summary", response_model=NarrativeSummaryOut, dependencies=[Depends(get_current_user)])
def narrative_summary(mode: str = Query(default="template", pattern="^(template|llm)$")) -> NarrativeSummaryOut:
    """On-demand, not polled: an LLM call has real latency and cost, unlike
    the rest of this router. mode="llm" falls back to "template" (reported
    via mode_used) whenever no provider is configured or the call fails --
    this endpoint never errors out just because the optional LLM path isn't
    available."""
    entries = history.get_history(limit=20)
    text, mode_used = summary_module.build_summary(entries, use_llm=(mode == "llm"))
    return NarrativeSummaryOut(
        text=text,
        mode_used=mode_used,
        llm_provider=llm_providers.active_provider() if mode_used == "llm" else None,
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
