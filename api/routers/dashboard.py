# -*- coding: utf-8 -*-
"""GET /dashboard/summary -- backs the React "Inicio" page (F-05)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from webapp import history, scheduler as sched_module, tasks, workflow_engine

from ..dependencies import get_current_user
from ..schemas.dashboard import DashboardSummaryOut, RecentRunOut

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
