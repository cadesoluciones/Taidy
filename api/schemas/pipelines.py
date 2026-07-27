# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel


class PipelineActivityOut(BaseModel):
    name: str
    type: str
    depends_on: List[Dict[str, Any]]


class PipelineDependenciesOut(BaseModel):
    activities: List[PipelineActivityOut]
