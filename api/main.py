# -*- coding: utf-8 -*-
"""
Taidy API -- FastAPI backend.

A thin layer over the existing webapp/*.py modules (themselves a thin layer
over src/**, per this project's long-standing rule: business logic lives in
src/ and is never reimplemented in the UI layer).

Run locally with: uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from webapp import scheduler as sched_module  # noqa: E402

from .routers import (  # noqa: E402
    audit as audit_router,
    auth as auth_router,
    dashboard as dashboard_router,
    history as history_router,
    meta as meta_router,
    schedules as schedules_router,
    tasks as tasks_router,
    users as users_router,
    workflows as workflows_router,
)

logger = logging.getLogger("taidy.api")

# Vite's dev server origin. Deliberately 127.0.0.1, not localhost: the
# session cookie has no explicit Domain (host-only, matching the exact
# backend host) and is SameSite=Lax -- "localhost" and "127.0.0.1" are
# different *sites* for SameSite purposes even though both are loopback, so
# mixing them silently drops the cookie on every cross-site fetch. Add the
# real production origin here once one exists -- never "*".
_ALLOWED_ORIGINS = ["http://127.0.0.1:5173"]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Built once per process, re-registers every persisted schedule.json entry.
    app.state.scheduler = sched_module.build_scheduler()
    try:
        yield
    finally:
        app.state.scheduler.shutdown(wait=False)


def create_app() -> FastAPI:
    app = FastAPI(title="Taidy API", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # Mirrors .streamlit/config.toml's showErrorDetails = "none": the client
        # never sees a stack trace, file paths, or internal function names --
        # only the server's own logs do.
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "Ha ocurrido un error interno. Consulta los registros del servidor."},
        )

    app.include_router(auth_router.router)
    app.include_router(dashboard_router.router)
    app.include_router(history_router.router)
    app.include_router(audit_router.router)
    app.include_router(users_router.router)
    app.include_router(schedules_router.router)
    app.include_router(workflows_router.router)
    app.include_router(workflows_router.runs_router)
    app.include_router(tasks_router.router)
    app.include_router(meta_router.router)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
