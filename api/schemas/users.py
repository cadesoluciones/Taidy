# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class UserOut(BaseModel):
    username: str
    role: str
    must_change_password: bool
    locked_until: Optional[str] = None


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=8)
    role: str


class ChangeRoleRequest(BaseModel):
    role: str


class UserListOut(BaseModel):
    items: List[UserOut]


class SessionOut(BaseModel):
    session_ref: str
    created_at: str


class SessionListOut(BaseModel):
    items: List[SessionOut]
