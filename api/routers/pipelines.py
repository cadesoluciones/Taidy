# -*- coding: utf-8 -*-
"""
GET /pipelines/{name}/dependencies -- fetches a Fabric Data Pipeline's
activities and their dependencies (via the Fabric REST API's getDefinition)
so the UI can draw them as a diagram, exactly like a saved NEXUS-BDB workflow.

Read-only and Operator+Admin gated, same as /ejecutar/pipelines (the page
this backs). Unlike everything else this session, this makes a REAL,
synchronous call to Microsoft Fabric using the same tenant/client credentials
already used to trigger pipeline runs (src/fabric_pipelines/config.py) --
never mocked, never cached, and never invoked unless a caller explicitly
asks for one pipeline's dependencies.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from src.fabric_pipelines.api import FabricPipelineClient, FabricPipelineError, extract_activities, parse_pipeline_definition
from src.fabric_pipelines.config import load_settings
from webapp.users_db import ROLE_ADMIN, ROLE_OPERATOR

from ..dependencies import require_any_role
from ..schemas.pipelines import PipelineActivityOut, PipelineDependenciesOut

router = APIRouter(
    prefix="/pipelines",
    tags=["pipelines"],
    dependencies=[Depends(require_any_role([ROLE_OPERATOR, ROLE_ADMIN]))],
)


@router.get("/{name}/dependencies", response_model=PipelineDependenciesOut)
def pipeline_dependencies(name: str) -> PipelineDependenciesOut:
    try:
        settings = load_settings()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Fabric no está configurado: {exc}"
        )

    try:
        pipeline = settings.get_pipeline(name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    client = FabricPipelineClient(settings)
    try:
        definition = client.get_definition(pipeline.item_id)
        pipeline_json = parse_pipeline_definition(definition)
        activities = extract_activities(pipeline_json)
    except FabricPipelineError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    return PipelineDependenciesOut(activities=[PipelineActivityOut(**a) for a in activities])
