# -*- coding: utf-8 -*-
"""
/workflows (definitions CRUD) and /workflow-runs (live executions) --
mirrors webapp/app.py:page_workflows. Designing/deleting a workflow
definition requires Admin; launching/stopping a run requires Operator+Admin,
and stopping additionally requires owning the run (or being Admin) -- the
exact same two-part check `_confirm_stop_workflow` makes in the Streamlit app.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from webapp import workflow_engine, workflows as workflows_module
from webapp.users_db import ROLE_ADMIN, ROLE_OPERATOR

from ..dependencies import CurrentUser, get_current_user, require_any_role, require_role
from ..schemas.workflows import (
    CreateWorkflowRequest,
    StepRunOut,
    WorkflowListOut,
    WorkflowOut,
    WorkflowRunListOut,
    WorkflowRunOut,
)

router = APIRouter(prefix="/workflows", tags=["workflows"], dependencies=[Depends(get_current_user)])
runs_router = APIRouter(prefix="/workflow-runs", tags=["workflows"], dependencies=[Depends(get_current_user)])

_ROLES_OPERATE = [ROLE_OPERATOR, ROLE_ADMIN]


@router.get("", response_model=WorkflowListOut)
def list_workflows() -> WorkflowListOut:
    return WorkflowListOut(items=[WorkflowOut(**w) for w in workflows_module.list_workflows()])


@router.post("", response_model=WorkflowOut, dependencies=[Depends(require_role(ROLE_ADMIN))])
def create_workflow(payload: CreateWorkflowRequest) -> WorkflowOut:
    try:
        workflow = workflows_module.create_workflow(payload.name, [s.model_dump() for s in payload.steps])
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return WorkflowOut(**workflow)


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_role(ROLE_ADMIN))])
def delete_workflow(workflow_id: str) -> None:
    workflows_module.delete_workflow(workflow_id)


@router.post("/{workflow_id}/run", response_model=WorkflowRunOut, dependencies=[Depends(require_any_role(_ROLES_OPERATE))])
def run_workflow(workflow_id: str, current: CurrentUser = Depends(get_current_user)) -> WorkflowRunOut:
    try:
        run = workflow_engine.start_workflow(workflow_id, current.username)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return _run_to_out(run)


def _run_to_out(run) -> WorkflowRunOut:
    return WorkflowRunOut(
        id=run.id,
        workflow_id=run.workflow_id,
        workflow_name=run.workflow_name,
        triggered_by=run.triggered_by,
        started_at=run.started_at,
        finished_at=run.finished_at,
        status=run.status,
        duration_seconds=run.duration_seconds(),
        steps=[
            StepRunOut(
                id=s.id,
                label=s.label,
                action=s.action,
                depends_on=s.depends_on,
                trigger_rule=s.trigger_rule,
                status=s.status,
                task_id=s.task_id,
            )
            for s in run.steps.values()
        ],
    )


@runs_router.get("", response_model=WorkflowRunListOut)
def list_workflow_runs() -> WorkflowRunListOut:
    return WorkflowRunListOut(items=[_run_to_out(r) for r in workflow_engine.list_runs()])


@runs_router.post("/{run_id}/stop", status_code=status.HTTP_204_NO_CONTENT)
def stop_workflow_run(run_id: str, current: CurrentUser = Depends(get_current_user)) -> None:
    run = workflow_engine.get_run(run_id)
    owns = run is not None and (current.role == ROLE_ADMIN or run.triggered_by == current.username)
    if not owns:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Solo puedes detener tus propios flujos (o tener el rol Admin)."
        )
    if current.role not in _ROLES_OPERATE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Detener un flujo requiere rol App.Operator o App.Admin."
        )
    workflow_engine.stop_workflow(run_id)
