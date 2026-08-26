# -*- coding: utf-8 -*-
"""Read-only options for form dropdowns -- adapter.py's table/pipeline
lists, already mtime-cached there (Fase 9), so this is a cheap passthrough.

Also exposes add/delete over tables.yaml and factorial_tables.yaml
(webapp/table_configs.py) so new tables can be registered from the web UI
instead of hand-editing YAML on the server -- gated to Admin, same as any
other structural config change (create workflow, reset checkpoints)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from webapp import adapter, table_configs
from webapp.users_db import ROLE_ADMIN

from ..dependencies import get_current_user, require_role
from ..schemas.meta import (
    AvailableProperty,
    AvailablePropertiesOut,
    BcTableListOut,
    BcTableOut,
    CreateBcTableRequest,
    CreateFactorialTableRequest,
    CreateHubspotTableRequest,
    FactorialTableListOut,
    FactorialTableOut,
    HubspotTableListOut,
    HubspotTableOut,
    PipelineListOut,
    TableListOut,
    UpdateBcTableRequest,
    UpdateFactorialTableRequest,
    UpdateHubspotTableRequest,
)

router = APIRouter(prefix="/meta", tags=["meta"], dependencies=[Depends(get_current_user)])


@router.get("/bc-tables", response_model=TableListOut)
def bc_tables() -> TableListOut:
    return TableListOut(items=adapter.list_bc_tables())


@router.get("/factorial-tables", response_model=TableListOut)
def factorial_tables() -> TableListOut:
    return TableListOut(items=adapter.list_factorial_tables())


@router.get("/hubspot-tables", response_model=TableListOut)
def hubspot_tables() -> TableListOut:
    return TableListOut(items=adapter.list_hubspot_tables())


@router.get("/pipelines", response_model=PipelineListOut)
def pipelines() -> PipelineListOut:
    return PipelineListOut(items=adapter.list_fabric_pipelines())


@router.get("/bc-tables/full", response_model=BcTableListOut)
def bc_tables_full() -> BcTableListOut:
    return BcTableListOut(items=[BcTableOut(**t) for t in table_configs.list_bc_tables_full()])


@router.post("/bc-tables", response_model=BcTableOut, dependencies=[Depends(require_role(ROLE_ADMIN))])
def create_bc_table(payload: CreateBcTableRequest) -> BcTableOut:
    try:
        entry = table_configs.add_bc_table(
            payload.name, payload.url, description=payload.description, incremental=payload.incremental
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return BcTableOut(**entry)


@router.patch("/bc-tables/{name}", response_model=BcTableOut, dependencies=[Depends(require_role(ROLE_ADMIN))])
def update_bc_table(name: str, payload: UpdateBcTableRequest) -> BcTableOut:
    try:
        entry = table_configs.update_bc_table(
            name,
            payload.url,
            description=payload.description,
            incremental=payload.incremental,
            new_name=payload.name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return BcTableOut(**entry)


@router.delete(
    "/bc-tables/{name}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_role(ROLE_ADMIN))]
)
def delete_bc_table(name: str) -> None:
    table_configs.delete_bc_table(name)


@router.get("/bc-tables/{name}/fields", response_model=TableListOut)
def bc_table_fields(name: str) -> TableListOut:
    return TableListOut(items=table_configs.bc_table_fields(name))


def _bc_client():
    from src.bc_client.api import BusinessCentralClient
    from src.bc_client.auth import OAuthTokenProvider
    from src.bc_client.config import load_settings as load_bc_settings

    settings = load_bc_settings()
    provider = OAuthTokenProvider(
        token_url=settings.token_url,
        client_id=settings.client_id,
        client_secret=settings.client_secret,
        scope=settings.scope,
    )
    return BusinessCentralClient(settings=settings, token_provider=provider)


@router.get(
    "/bc-tables/available-odata-tables",
    response_model=AvailablePropertiesOut,
    dependencies=[Depends(require_role(ROLE_ADMIN))],
)
def bc_available_odata_tables() -> AvailablePropertiesOut:
    """Live discovery of every entity set Business Central's standard
    OData v4 service exposes, to help pick a `url` when registering a new
    table (see BusinessCentralClient.list_available_odata_tables). Needs
    an existing BC table using that mechanism to deduce the tenant/
    environment from -- same constraint the extraction pipeline itself
    already has."""
    from dotenv import load_dotenv

    from src.bc_client.api import BusinessCentralError

    load_dotenv()
    try:
        tables = _bc_client().list_available_odata_tables()
    except (ValueError, BusinessCentralError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return AvailablePropertiesOut(items=[AvailableProperty(**t) for t in tables])


@router.get(
    "/bc-tables/available-custom-api-tables",
    response_model=AvailablePropertiesOut,
    dependencies=[Depends(require_role(ROLE_ADMIN))],
)
def bc_available_custom_api_tables() -> AvailablePropertiesOut:
    """Live discovery of every entity exposed by BC's "Custom APIs"
    mechanism, for every publisher/group/version already used by at least
    one currently-configured table (see
    BusinessCentralClient.list_available_custom_api_tables)."""
    from dotenv import load_dotenv

    from src.bc_client.api import BusinessCentralError

    load_dotenv()
    try:
        tables = _bc_client().list_available_custom_api_tables()
    except (ValueError, BusinessCentralError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return AvailablePropertiesOut(items=[AvailableProperty(**t) for t in tables])


@router.get("/factorial-tables/full", response_model=FactorialTableListOut)
def factorial_tables_full() -> FactorialTableListOut:
    return FactorialTableListOut(items=[FactorialTableOut(**t) for t in table_configs.list_factorial_tables_full()])


@router.post(
    "/factorial-tables", response_model=FactorialTableOut, dependencies=[Depends(require_role(ROLE_ADMIN))]
)
def create_factorial_table(payload: CreateFactorialTableRequest) -> FactorialTableOut:
    try:
        entry = table_configs.add_factorial_table(
            payload.name,
            payload.path,
            payload.fields,
            description=payload.description,
            date_range=payload.date_range,
            employee_filter=payload.employee_filter,
            incremental=payload.incremental,
            overlap_days=payload.overlap_days,
            chunk_days=payload.chunk_days,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return FactorialTableOut(**entry)


@router.patch(
    "/factorial-tables/{name}", response_model=FactorialTableOut, dependencies=[Depends(require_role(ROLE_ADMIN))]
)
def update_factorial_table(name: str, payload: UpdateFactorialTableRequest) -> FactorialTableOut:
    try:
        entry = table_configs.update_factorial_table(
            name,
            payload.path,
            payload.fields,
            description=payload.description,
            date_range=payload.date_range,
            employee_filter=payload.employee_filter,
            incremental=payload.incremental,
            overlap_days=payload.overlap_days,
            chunk_days=payload.chunk_days,
            new_name=payload.name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return FactorialTableOut(**entry)


@router.delete(
    "/factorial-tables/{name}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(ROLE_ADMIN))],
)
def delete_factorial_table(name: str) -> None:
    table_configs.delete_factorial_table(name)


@router.get(
    "/factorial-tables/available-fields",
    response_model=AvailablePropertiesOut,
    dependencies=[Depends(require_role(ROLE_ADMIN))],
)
def factorial_available_fields(path: str, date_range: bool = False) -> AvailablePropertiesOut:
    """Live "peek" at a Factorial endpoint to help pick which fields to keep
    when registering a table -- Factorial has no schema/properties endpoint,
    so this samples real data and returns the field names actually seen
    (see FactorialClient.sample_fields)."""
    from dotenv import load_dotenv

    from src.factorial_client.api import FactorialClient, FactorialError
    from src.factorial_client.config import load_settings as load_factorial_settings

    load_dotenv()
    path = path.strip()
    if not path:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Indica la ruta de la API de Factorial.")

    try:
        settings = load_factorial_settings()
        client = FactorialClient(settings=settings)
        names = client.sample_fields(path=path, date_range=date_range)
    except (ValueError, FactorialError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return AvailablePropertiesOut(items=[AvailableProperty(name=n) for n in names])


@router.get(
    "/factorial-tables/available-tables",
    response_model=AvailablePropertiesOut,
    dependencies=[Depends(require_role(ROLE_ADMIN))],
)
def factorial_available_tables() -> AvailablePropertiesOut:
    """Live discovery of every readable endpoint in Factorial's public API,
    to help pick a `path` when registering a new table (see
    FactorialClient.list_available_tables). Unlike available-fields, this
    needs no input -- Factorial's OpenAPI spec is self-contained."""
    from dotenv import load_dotenv

    from src.factorial_client.api import FactorialClient, FactorialError
    from src.factorial_client.config import load_settings as load_factorial_settings

    load_dotenv()
    try:
        settings = load_factorial_settings()
        client = FactorialClient(settings=settings)
        tables = client.list_available_tables()
    except (ValueError, FactorialError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return AvailablePropertiesOut(items=[AvailableProperty(**t) for t in tables])


@router.get("/hubspot-tables/full", response_model=HubspotTableListOut)
def hubspot_tables_full() -> HubspotTableListOut:
    return HubspotTableListOut(items=[HubspotTableOut(**t) for t in table_configs.list_hubspot_tables_full()])


@router.post("/hubspot-tables", response_model=HubspotTableOut, dependencies=[Depends(require_role(ROLE_ADMIN))])
def create_hubspot_table(payload: CreateHubspotTableRequest) -> HubspotTableOut:
    try:
        entry = table_configs.add_hubspot_table(
            payload.name, payload.object_type, payload.fields, description=payload.description
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return HubspotTableOut(**entry)


@router.patch(
    "/hubspot-tables/{name}", response_model=HubspotTableOut, dependencies=[Depends(require_role(ROLE_ADMIN))]
)
def update_hubspot_table(name: str, payload: UpdateHubspotTableRequest) -> HubspotTableOut:
    try:
        entry = table_configs.update_hubspot_table(
            name, payload.object_type, payload.fields, description=payload.description, new_name=payload.name
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return HubspotTableOut(**entry)


@router.delete(
    "/hubspot-tables/{name}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(ROLE_ADMIN))],
)
def delete_hubspot_table(name: str) -> None:
    table_configs.delete_hubspot_table(name)


@router.get(
    "/hubspot-tables/available-properties",
    response_model=AvailablePropertiesOut,
    dependencies=[Depends(require_role(ROLE_ADMIN))],
)
def hubspot_available_properties(object_type: str, include_hidden: bool = False) -> AvailablePropertiesOut:
    """Live discovery of every property HubSpot exposes for a CRM object
    type, to help pick which ones to keep when registering a table (see
    HubspotClient.list_properties). Takes a raw object_type, not a saved
    table name, so it works even before the table entry exists."""
    from dotenv import load_dotenv

    from src.hubspot_client.api import HubspotClient, HubspotError
    from src.hubspot_client.config import load_settings as load_hubspot_settings

    load_dotenv()
    object_type = object_type.strip()
    if not object_type:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Indica el tipo de objeto de HubSpot.")

    try:
        settings = load_hubspot_settings()
        client = HubspotClient(settings=settings)
        properties = client.list_properties(object_type, include_hidden=include_hidden)
    except (ValueError, HubspotError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return AvailablePropertiesOut(items=[AvailableProperty(name=p["name"], label=p["label"]) for p in properties])


@router.get(
    "/hubspot-tables/available-object-types",
    response_model=AvailablePropertiesOut,
    dependencies=[Depends(require_role(ROLE_ADMIN))],
)
def hubspot_available_object_types() -> AvailablePropertiesOut:
    """Every CRM object type this portal could plausibly extract from, to
    help pick `object_type` when registering a new table (see
    HubspotClient.list_object_types). Needs no input -- always includes the
    fixed standard objects, plus this portal's custom objects when the
    Private App token has the scope to list them."""
    from dotenv import load_dotenv

    from src.hubspot_client.api import HubspotClient, HubspotError
    from src.hubspot_client.config import load_settings as load_hubspot_settings

    load_dotenv()
    try:
        settings = load_hubspot_settings()
        client = HubspotClient(settings=settings)
        types = client.list_object_types()
    except (ValueError, HubspotError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return AvailablePropertiesOut(items=[AvailableProperty(**t) for t in types])
