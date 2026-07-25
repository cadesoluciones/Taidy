# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date
from typing import List, Optional

from pydantic import BaseModel


class ExtractBcRequest(BaseModel):
    tables: Optional[List[str]] = None
    output_dir: str = ""
    page_size: Optional[int] = None
    mode: str = "incremental"
    parallel: int = 1
    dry_run: bool = False
    reset_watermarks: bool = False
    checkpoint_path: str = ""
    verbose: bool = False
    notify: bool = False


class UploadBcRequest(BaseModel):
    output_dir: str = "./exports"
    dry_run: bool = False
    skip_existing: bool = False
    verbose: bool = False
    notify: bool = False


class SyncBcRequest(BaseModel):
    tables: Optional[List[str]] = None
    output_dir: str = "./exports"
    mode: str = "incremental"
    parallel: int = 1
    dry_run: bool = False
    skip_existing: bool = False
    verbose: bool = False
    notify: bool = False


class ExtractFactorialRequest(BaseModel):
    start_on: date
    end_on: date
    employees: Optional[List[int]] = None
    employee_status: str = "active"
    tables: Optional[List[str]] = None
    output_dir: str = ""
    mode: str = "full"
    parallel: int = 5
    reset_all_checkpoints: bool = False
    dry_run: bool = False
    verbose: bool = False
    notify: bool = False


class UploadFactorialRequest(BaseModel):
    output_dir: str = "./exports_factorial"
    tables: Optional[List[str]] = None
    dry_run: bool = False
    skip_existing: bool = False
    verbose: bool = False
    notify: bool = False


class SyncFactorialRequest(BaseModel):
    start_on: date
    end_on: date
    employee_status: str = "active"
    tables: Optional[List[str]] = None
    output_dir: str = "./exports_factorial"
    mode: str = "incremental"
    parallel: int = 5
    dry_run: bool = False
    skip_existing: bool = False
    verbose: bool = False
    notify: bool = False


class RunPipelineRequest(BaseModel):
    pipeline: str
    wait: bool = True
    poll_seconds: int = 15
    verbose: bool = False
    notify: bool = False


class TableStatusOut(BaseModel):
    name: str
    status: str
    detail: str = ""
    phase: str = ""


class TaskOut(BaseModel):
    id: str
    action: str
    action_label: str
    triggered_by: str
    status: str
    started_at: str
    finished_at: Optional[str] = None
    duration_seconds: float
    current_step: int
    step_labels: List[str]
    table_statuses: List[TableStatusOut]


class TaskListOut(BaseModel):
    items: List[TaskOut]
