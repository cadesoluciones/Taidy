# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import List

from pydantic import BaseModel


class EnvFieldOut(BaseModel):
    key: str
    label: str
    group: str
    secret: bool
    value: str


class EnvFieldListOut(BaseModel):
    items: List[EnvFieldOut]


class UpdateEnvFieldRequest(BaseModel):
    value: str


class TestConnectionOut(BaseModel):
    ok: bool
    message: str
