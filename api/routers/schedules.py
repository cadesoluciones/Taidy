# -*- coding: utf-8 -*-
"""/schedules -- list is visible to any authenticated user (mirrors
webapp/app.py:page_schedules showing the existing list to everyone); create/
enable/disable/delete require Admin, exactly like the Streamlit page."""

from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import APIRouter, Depends, HTTPException, status

from webapp import scheduler as sched_module
from webapp.users_db import ROLE_ADMIN

from ..dependencies import get_current_user, get_scheduler, require_role
from ..schemas.schedules import (
    CreateScheduleRequest,
    ScheduleListOut,
    ScheduleOut,
    ScheduleWeekOut,
    SetScheduleEnabledRequest,
)

router = APIRouter(prefix="/schedules", tags=["schedules"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=ScheduleListOut)
def list_schedules() -> ScheduleListOut:
    return ScheduleListOut(items=[ScheduleOut(**s) for s in sched_module.list_schedules()])


@router.get("/week", response_model=ScheduleWeekOut)
def schedules_week() -> ScheduleWeekOut:
    """Backs Inicio's weekly calendar: schedule_id -> ISO datetimes it's due
    to fire between this week's Monday and Sunday."""
    return ScheduleWeekOut(occurrences=sched_module.week_occurrences())


@router.post("", response_model=ScheduleOut, dependencies=[Depends(require_role(ROLE_ADMIN))])
def create_schedule(
    payload: CreateScheduleRequest,
    scheduler: BackgroundScheduler = Depends(get_scheduler),
) -> ScheduleOut:
    try:
        schedule = sched_module.add_schedule(
            scheduler,
            name=payload.name,
            action=payload.action,
            params=payload.params,
            trigger=payload.trigger,
            trigger_args=payload.trigger_args,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return ScheduleOut(**schedule)


@router.put("/{schedule_id}", response_model=ScheduleOut, dependencies=[Depends(require_role(ROLE_ADMIN))])
def update_schedule(
    schedule_id: str,
    payload: CreateScheduleRequest,
    scheduler: BackgroundScheduler = Depends(get_scheduler),
) -> ScheduleOut:
    """Full edit of an existing schedule's config (name/action/params/
    trigger) -- distinct from the PATCH below, which only ever flips
    `enabled`. Keeps the schedule's id/created_at/enabled state; see
    webapp/scheduler.py::update_schedule for how the live APScheduler job
    is (or isn't) replaced."""
    try:
        schedule = sched_module.update_schedule(
            scheduler,
            schedule_id,
            name=payload.name,
            action=payload.action,
            params=payload.params,
            trigger=payload.trigger,
            trigger_args=payload.trigger_args,
        )
    except ValueError as exc:
        detail = str(exc)
        code = (
            status.HTTP_404_NOT_FOUND
            if detail.startswith("Tarea programada desconocida")
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=code, detail=detail)
    return ScheduleOut(**schedule)


@router.patch("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_role(ROLE_ADMIN))])
def set_schedule_enabled(
    schedule_id: str,
    payload: SetScheduleEnabledRequest,
    scheduler: BackgroundScheduler = Depends(get_scheduler),
) -> None:
    sched_module.set_schedule_enabled(scheduler, schedule_id, payload.enabled)


@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_role(ROLE_ADMIN))])
def delete_schedule(schedule_id: str, scheduler: BackgroundScheduler = Depends(get_scheduler)) -> None:
    sched_module.remove_schedule(scheduler, schedule_id)
