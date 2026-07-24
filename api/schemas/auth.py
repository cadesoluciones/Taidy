# -*- coding: utf-8 -*-
from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    new_password: str = Field(min_length=8)
    confirm_password: str


class UserSessionOut(BaseModel):
    username: str
    role: str
    must_change_password: bool
