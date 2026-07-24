# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import List

from pydantic import BaseModel


class TableListOut(BaseModel):
    items: List[str]


class PipelineListOut(BaseModel):
    items: List[str]
