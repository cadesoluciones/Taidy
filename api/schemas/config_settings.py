# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import List, Union

from pydantic import BaseModel

ConfigFieldValue = Union[bool, int, str, List[str]]


class ConfigFieldOut(BaseModel):
    key: str
    label: str
    group: str
    kind: str
    value: ConfigFieldValue


class ConfigFieldListOut(BaseModel):
    items: List[ConfigFieldOut]


class UpdateConfigFieldRequest(BaseModel):
    value: ConfigFieldValue


class PipelineOut(BaseModel):
    name: str
    item_id: str


class PipelineListOut(BaseModel):
    items: List[PipelineOut]


class SetPipelinesRequest(BaseModel):
    items: List[PipelineOut]
