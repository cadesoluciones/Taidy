# -*- coding: utf-8 -*-
"""
Client for Microsoft Fabric's "run item job on demand" REST API, used to
trigger a Data Factory pipeline and poll its status.

Reference: POST/GET .../workspaces/{workspaceId}/items/{itemId}/jobs/instances
"""

from __future__ import annotations

import base64
import json
import time
from typing import Any, Dict, List, Optional

import requests
from azure.identity import ClientSecretCredential
from requests.exceptions import ChunkedEncodingError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .config import Settings
from ..utils import get_logger

logger = get_logger(__name__)

_FABRIC_API_BASE = "https://api.fabric.microsoft.com/v1"
_FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"

# Terminal job statuses per the Fabric API; anything else means still running.
TERMINAL_STATUSES = {"Completed", "Failed", "Cancelled", "Deduped"}

# getDefinition can be a long-running operation (202 + Location header to
# poll) instead of an immediate 200 -- these bound how long we're willing to
# wait for Fabric to finish assembling the definition.
_MAX_OPERATION_POLLS = 30
_DEFAULT_POLL_INTERVAL_SECONDS = 2.0


class FabricPipelineError(RuntimeError):
    """Raised for Fabric pipeline API errors (bad response, missing job id, ...)."""


class FabricPipelineClient:
    def __init__(
        self,
        settings: Settings,
        *,
        session: Optional[requests.Session] = None,
        timeout: float = 30.0,
    ) -> None:
        self._settings = settings
        self._session = session or requests.Session()
        self._timeout = timeout
        self._credential = ClientSecretCredential(
            tenant_id=settings.tenant_id,
            client_id=settings.client_id,
            client_secret=settings.client_secret,
        )

    def _headers(self) -> Dict[str, str]:
        token = self._credential.get_token(_FABRIC_SCOPE)
        return {"Authorization": f"Bearer {token.token}", "Content-Type": "application/json"}

    # Retries only transient, transport-level failures (dropped connection,
    # timeout) -- same policy as src/bc_client/api.py's _get. A bad HTTP
    # status from Fabric itself (auth rejected, pipeline not found, ...) is
    # not a transient condition and is handled by each caller as before.
    @retry(
        retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout, ChunkedEncodingError)),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        return self._session.request(method, url, timeout=self._timeout, **kwargs)

    def trigger_run(self, item_id: str) -> str:
        """Starts an on-demand pipeline run. Returns the job instance id."""
        url = f"{_FABRIC_API_BASE}/workspaces/{self._settings.workspace_id}/items/{item_id}/jobs/instances"
        response = self._request(
            "POST",
            url,
            headers=self._headers(),
            params={"jobType": "Pipeline"},
            json={},
        )
        if response.status_code not in (200, 202):
            raise FabricPipelineError(
                f"No se pudo lanzar el pipeline (HTTP {response.status_code}): {response.text}"
            )
        location = response.headers.get("Location", "")
        job_instance_id = location.rstrip("/").rsplit("/", 1)[-1] if location else ""
        if not job_instance_id:
            raise FabricPipelineError(
                "Fabric no devolvió un identificador de ejecución (cabecera 'Location' vacía o ausente)."
            )
        return job_instance_id

    def list_pipelines(self) -> List[Dict[str, str]]:
        """Discovers Data Pipeline items in the configured workspace via the Fabric API
        (GET .../items?type=DataPipeline), so pipelines don't have to be found by hand
        in the portal. Returns [{"name": ..., "item_id": ...}, ...], paginated internally.
        """
        url = f"{_FABRIC_API_BASE}/workspaces/{self._settings.workspace_id}/items"
        results: List[Dict[str, str]] = []
        params: Dict[str, str] = {"type": "DataPipeline"}
        while True:
            response = self._request("GET", url, headers=self._headers(), params=params)
            if response.status_code != 200:
                raise FabricPipelineError(
                    f"No se pudo listar los pipelines (HTTP {response.status_code}): {response.text}"
                )
            payload = response.json()
            for item in payload.get("value", []):
                results.append({"name": item.get("displayName", ""), "item_id": item.get("id", "")})
            token = payload.get("continuationToken")
            if not token:
                break
            params = {"type": "DataPipeline", "continuationToken": token}
        return results

    def list_items(self) -> List[Dict[str, Any]]:
        """Every item in the workspace (any type -- Notebook, DataPipeline,
        Lakehouse, Warehouse, Report, ...), paginated. Each dict has at least
        id/type/displayName/description; `folderId` is present only for
        items not sitting at the workspace root. Backs the Fabric catalog
        (webapp/fabric_catalog.py) -- purely a read, never mocked or cached,
        same as list_pipelines()."""
        url = f"{_FABRIC_API_BASE}/workspaces/{self._settings.workspace_id}/items"
        results: List[Dict[str, Any]] = []
        params: Dict[str, str] = {}
        while True:
            response = self._request("GET", url, headers=self._headers(), params=params)
            if response.status_code != 200:
                raise FabricPipelineError(
                    f"No se pudieron listar los elementos del workspace (HTTP {response.status_code}): {response.text}"
                )
            payload = response.json()
            results.extend(payload.get("value", []))
            token = payload.get("continuationToken")
            if not token:
                break
            params = {"continuationToken": token}
        return results

    def list_folders(self) -> List[Dict[str, Any]]:
        """Every folder in the workspace (id/displayName/parentFolderId --
        root folders have no parentFolderId), paginated. Combined with
        list_items()'s `folderId` to rebuild the full path shown in Fabric's
        own UI (e.g. "ETLs Medallion/silver")."""
        url = f"{_FABRIC_API_BASE}/workspaces/{self._settings.workspace_id}/folders"
        results: List[Dict[str, Any]] = []
        params: Dict[str, str] = {}
        while True:
            response = self._request("GET", url, headers=self._headers(), params=params)
            if response.status_code != 200:
                raise FabricPipelineError(
                    f"No se pudieron listar las carpetas del workspace (HTTP {response.status_code}): {response.text}"
                )
            payload = response.json()
            results.extend(payload.get("value", []))
            token = payload.get("continuationToken")
            if not token:
                break
            params = {"continuationToken": token}
        return results

    def get_status(self, item_id: str, job_instance_id: str) -> Dict[str, Any]:
        url = (
            f"{_FABRIC_API_BASE}/workspaces/{self._settings.workspace_id}/items/{item_id}"
            f"/jobs/instances/{job_instance_id}"
        )
        response = self._request("GET", url, headers=self._headers())
        if response.status_code != 200:
            raise FabricPipelineError(
                f"No se pudo consultar el estado del pipeline (HTTP {response.status_code}): {response.text}"
            )
        return response.json()

    def get_definition(self, item_id: str) -> Dict[str, Any]:
        """Fetches a Data Pipeline item's definition (its activities and
        their dependencies) via Fabric's item-content API. Like most Fabric
        item operations this can be either an immediate 200 or a
        long-running operation (202 + a Location header to poll)."""
        url = f"{_FABRIC_API_BASE}/workspaces/{self._settings.workspace_id}/items/{item_id}/getDefinition"
        response = self._request("POST", url, headers=self._headers())
        if response.status_code == 200:
            return response.json()
        if response.status_code == 202:
            return self._await_operation(response)
        raise FabricPipelineError(
            f"No se pudo obtener la definición del pipeline (HTTP {response.status_code}): {response.text}"
        )

    def _await_operation(self, initial_response: requests.Response) -> Dict[str, Any]:
        operation_url = initial_response.headers.get("Location")
        if not operation_url:
            raise FabricPipelineError(
                "Fabric aceptó la solicitud (202) pero no devolvió una URL de operación para consultarla "
                "('Location' vacía o ausente)."
            )
        try:
            poll_interval = float(initial_response.headers.get("Retry-After", _DEFAULT_POLL_INTERVAL_SECONDS))
        except ValueError:
            poll_interval = _DEFAULT_POLL_INTERVAL_SECONDS

        for _ in range(_MAX_OPERATION_POLLS):
            time.sleep(poll_interval)
            op_response = self._request("GET", operation_url, headers=self._headers())
            if op_response.status_code != 200:
                raise FabricPipelineError(
                    f"Error consultando el estado de la operación (HTTP {op_response.status_code}): {op_response.text}"
                )
            payload = op_response.json()
            op_status = payload.get("status")
            if op_status == "Succeeded":
                result_response = self._request("GET", f"{operation_url}/result", headers=self._headers())
                if result_response.status_code != 200:
                    raise FabricPipelineError(
                        f"No se pudo obtener el resultado de la operación (HTTP {result_response.status_code}): "
                        f"{result_response.text}"
                    )
                return result_response.json()
            if op_status == "Failed":
                raise FabricPipelineError(f"La operación de Fabric falló: {payload.get('error')}")
        raise FabricPipelineError("Tiempo de espera agotado consultando la definición del pipeline.")


def parse_pipeline_definition(definition: Dict[str, Any]) -> Dict[str, Any]:
    """Decodes the "pipeline-content.json" part of a Fabric item definition
    payload (base64, per Fabric's item-definition format) into the
    ADF-style {"properties": {"activities": [...]}} dict."""
    parts = definition.get("definition", {}).get("parts", [])
    for part in parts:
        if part.get("path", "").endswith("pipeline-content.json"):
            try:
                decoded = base64.b64decode(part.get("payload", "")).decode("utf-8")
                return json.loads(decoded)
            except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise FabricPipelineError(f"No se pudo decodificar la definición del pipeline: {exc}") from exc
    raise FabricPipelineError("La definición del pipeline no contiene 'pipeline-content.json'.")


def extract_activities(pipeline_definition: Dict[str, Any]) -> List[Dict[str, Any]]:
    """[{"name", "type", "depends_on": [{"activity", "conditions": [...]}]}]
    from an ADF-style pipeline definition -- activity names are unique
    within a pipeline, so they double as node ids for the diagram."""
    activities = pipeline_definition.get("properties", {}).get("activities", [])
    result: List[Dict[str, Any]] = []
    for activity in activities:
        depends_on = [
            {"activity": dep.get("activity"), "conditions": dep.get("dependencyConditions", [])}
            for dep in activity.get("dependsOn", [])
            if dep.get("activity")
        ]
        result.append({"name": activity.get("name"), "type": activity.get("type"), "depends_on": depends_on})
    return result
