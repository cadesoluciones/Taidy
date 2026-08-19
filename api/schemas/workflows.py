# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class StepIn(BaseModel):
    id: str
    label: str
    action: str
    params: Dict[str, Any] = {}
    depends_on: List[str] = []
    trigger_rule: str = "all_success"


class WorkflowOut(BaseModel):
    id: str
    name: str
    description: str = ""
    steps: List[StepIn]
    created_at: str
    reader_allowed_users: List[str] = []


class WorkflowListOut(BaseModel):
    items: List[WorkflowOut]


class CreateWorkflowRequest(BaseModel):
    name: str
    description: str = ""
    steps: List[StepIn]


class SetReaderAccessRequest(BaseModel):
    reader_usernames: List[str]


class RunWorkflowRequest(BaseModel):
    notify: bool = False


class StepRunOut(BaseModel):
    id: str
    label: str
    action: str
    depends_on: List[str]
    trigger_rule: str
    status: str
    task_id: Optional[str] = None


class WorkflowRunOut(BaseModel):
    id: str
    workflow_id: str
    workflow_name: str
    triggered_by: str
    started_at: str
    finished_at: Optional[str] = None
    status: str
    duration_seconds: float
    steps: List[StepRunOut]


class WorkflowRunListOut(BaseModel):
    items: List[WorkflowRunOut]
