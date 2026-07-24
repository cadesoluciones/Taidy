# -*- coding: utf-8 -*-
"""
/tasks -- launches the 7 actions webapp/app.py's "Ejecutar" pages expose,
plus list/detail/stop for "Tareas en curso" (F-06..F-13). Every launch
endpoint is a thin call into webapp/tasks.launch(), the exact same function
manual Streamlit buttons and scheduled runs already use -- no argv-building
or subprocess logic is duplicated here.
"""

from __future__ import annotations

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from webapp import adapter, tasks as tasks_module
from webapp.users_db import ROLE_ADMIN, ROLE_OPERATOR

from ..dependencies import CurrentUser, get_current_user, require_any_role
from ..schemas.tasks import (
    ExtractBcRequest,
    ExtractFactorialRequest,
    RunPipelineRequest,
    SyncBcRequest,
    SyncFactorialRequest,
    TableStatusOut,
    TaskListOut,
    TaskOut,
    UploadBcRequest,
    UploadFactorialRequest,
)

router = APIRouter(prefix="/tasks", tags=["tasks"], dependencies=[Depends(get_current_user)])

_ROLES_OPERATE = [ROLE_OPERATOR, ROLE_ADMIN]


def _launch(action: str, params: dict, current: CurrentUser) -> TaskOut:
    if current.role not in _ROLES_OPERATE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para ejecutar esta acción (requiere rol App.Operator o App.Admin).",
        )
    try:
        task = tasks_module.launch(action, params, current.username)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return _task_to_out(task)


def _task_to_out(task) -> TaskOut:
    return TaskOut(
        id=task.id,
        action=task.action,
        action_label=tasks_module.ACTION_LABELS.get(task.action, task.action),
        triggered_by=task.triggered_by,
        status=task.status,
        started_at=task.started_at,
        finished_at=task.finished_at,
        duration_seconds=task.duration_seconds(),
        current_step=task.current_step,
        step_labels=task.step_labels,
        table_statuses=[
            TableStatusOut(name=s.name, status=s.status, detail=s.detail, phase=s.phase) for s in task.table_statuses()
        ],
    )


@router.post("/extract-bc", response_model=TaskOut)
def extract_bc(payload: ExtractBcRequest, current: CurrentUser = Depends(get_current_user)) -> TaskOut:
    if payload.reset_watermarks and current.role != ROLE_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Resetear checkpoints es una operación crítica: requiere el rol App.Admin.",
        )
    params = payload.model_dump()
    # Normalized here, not just in the React form: webapp/app.py's
    # page_bc_extract never lets a literal 0 reach tasks.launch() ("0 = usa
    # el de config.json" is a UI convention, not a real page size), so a
    # caller hitting this endpoint directly must get the same behavior the
    # Streamlit form guarantees, not one that depends on the frontend having
    # already converted it.
    params["page_size"] = params["page_size"] or None
    return _launch("extract_bc", params, current)


@router.post("/upload-bc", response_model=TaskOut)
def upload_bc(payload: UploadBcRequest, current: CurrentUser = Depends(get_current_user)) -> TaskOut:
    return _launch("upload_bc", payload.model_dump(), current)


@router.post("/sync-bc", response_model=TaskOut)
def sync_bc(payload: SyncBcRequest, current: CurrentUser = Depends(get_current_user)) -> TaskOut:
    return _launch("sync_bc", payload.model_dump(), current)


@router.post("/extract-factorial", response_model=TaskOut)
def extract_factorial(payload: ExtractFactorialRequest, current: CurrentUser = Depends(get_current_user)) -> TaskOut:
    if payload.start_on > payload.end_on:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="'Desde' no puede ser posterior a 'Hasta'.")
    if payload.reset_all_checkpoints and current.role != ROLE_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Resetear checkpoints es una operación crítica: requiere el rol App.Admin.",
        )
    params = payload.model_dump()
    params["start_on"] = payload.start_on.isoformat()
    params["end_on"] = payload.end_on.isoformat()
    return _launch("extract_factorial", params, current)


@router.post("/upload-factorial", response_model=TaskOut)
def upload_factorial(payload: UploadFactorialRequest, current: CurrentUser = Depends(get_current_user)) -> TaskOut:
    return _launch("upload_factorial", payload.model_dump(), current)


@router.post("/sync-factorial", response_model=TaskOut)
def sync_factorial(payload: SyncFactorialRequest, current: CurrentUser = Depends(get_current_user)) -> TaskOut:
    if payload.start_on > payload.end_on:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="'Desde' no puede ser posterior a 'Hasta'.")
    params = payload.model_dump()
    params["start_on"] = payload.start_on.isoformat()
    params["end_on"] = payload.end_on.isoformat()
    return _launch("sync_factorial", params, current)


@router.post("/run-pipeline", response_model=TaskOut)
def run_pipeline(payload: RunPipelineRequest, current: CurrentUser = Depends(get_current_user)) -> TaskOut:
    return _launch("run_pipeline", payload.model_dump(), current)


@router.get("", response_model=TaskListOut)
def list_tasks(
    action: List[str] = Query(default=[]),
    user: List[str] = Query(default=[]),
    status_: List[str] = Query(default=[], alias="status"),
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
) -> TaskListOut:
    all_tasks = tasks_module.list_tasks()

    def _matches(t) -> bool:
        if action and t.action not in action:
            return False
        if user and t.triggered_by not in user:
            return False
        if status_ and t.status not in status_:
            return False
        if date_from or date_to:
            from datetime import datetime

            started_date = datetime.fromisoformat(t.started_at).date()
            if date_from and started_date < date_from:
                return False
            if date_to and started_date > date_to:
                return False
        return True

    return TaskListOut(items=[_task_to_out(t) for t in all_tasks if _matches(t)])


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: str) -> TaskOut:
    task = tasks_module.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tarea no encontrada.")
    return _task_to_out(task)


@router.post("/{task_id}/stop", status_code=status.HTTP_204_NO_CONTENT)
def stop_task(task_id: str, current: CurrentUser = Depends(get_current_user)) -> None:
    task = tasks_module.get_task(task_id)
    owns = task is not None and (current.role == ROLE_ADMIN or task.triggered_by == current.username)
    if not owns:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Solo puedes detener tus propias tareas (o tener el rol Admin)."
        )
    if current.role not in _ROLES_OPERATE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Detener una tarea requiere rol App.Operator o App.Admin."
        )
    tasks_module.stop_task(task_id)
