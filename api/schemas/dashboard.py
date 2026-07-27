# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel

from .workflows import WorkflowRunOut


class RecentRunOut(BaseModel):
    action: str
    source: str
    ok: bool
    status: str
    finished_at: str
    message: str


class ErrorRateAlertOut(BaseModel):
    action: str
    recent_failures: int
    recent_total: int


class DashboardSummaryOut(BaseModel):
    running_count: int
    active_schedule_count: int
    recent_error_count: int
    recent_history: List[RecentRunOut]
    error_rate_alerts: List[ErrorRateAlertOut]


class NarrativeSummaryOut(BaseModel):
    text: str
    mode_used: str  # "template" | "llm" -- may differ from the configured mode (see SummaryModeOut)
    llm_provider: Optional[str] = None


class SummaryModeOut(BaseModel):
    mode: str  # "template" | "llm"


class SetSummaryModeRequest(BaseModel):
    mode: str


class MyWorkflowStatusOut(BaseModel):
    id: str
    name: str
    current_run: Optional[WorkflowRunOut] = None
    last_run: Optional[WorkflowRunOut] = None
    scheduled: bool


class MyWorkflowsOut(BaseModel):
    items: List[MyWorkflowStatusOut]
