# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import List

from pydantic import BaseModel


class AuditEntryOut(BaseModel):
    ts: str
    event: str
    outcome: str
    user: str
    detail: str


class AuditPageOut(BaseModel):
    items: List[AuditEntryOut]
    total_matching: int
    total_available: int
