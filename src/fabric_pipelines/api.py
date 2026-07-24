# -*- coding: utf-8 -*-
"""
Client for Microsoft Fabric's "run item job on demand" REST API, used to
trigger a Data Factory pipeline and poll its status.

Reference: POST/GET .../workspaces/{workspaceId}/items/{itemId}/jobs/instances
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests
from azure.identity import ClientSecretCredential

from .config import Settings
from ..utils import get_logger

logger = get_logger(__name__)

_FABRIC_API_BASE = "https://api.fabric.microsoft.com/v1"
_FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"

# Terminal job statuses per the Fabric API; anything else means still running.
TERMINAL_STATUSES = {"Completed", "Failed", "Cancelled", "Deduped"}


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

    def trigger_run(self, item_id: str) -> str:
        """Starts an on-demand pipeline run. Returns the job instance id."""
        url = f"{_FABRIC_API_BASE}/workspaces/{self._settings.workspace_id}/items/{item_id}/jobs/instances"
        response = self._session.post(
            url,
            headers=self._headers(),
            params={"jobType": "Pipeline"},
            json={},
            timeout=self._timeout,
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
            response = self._session.get(url, headers=self._headers(), params=params, timeout=self._timeout)
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

    def get_status(self, item_id: str, job_instance_id: str) -> Dict[str, Any]:
        url = (
            f"{_FABRIC_API_BASE}/workspaces/{self._settings.workspace_id}/items/{item_id}"
            f"/jobs/instances/{job_instance_id}"
        )
        response = self._session.get(url, headers=self._headers(), timeout=self._timeout)
        if response.status_code != 200:
            raise FabricPipelineError(
                f"No se pudo consultar el estado del pipeline (HTTP {response.status_code}): {response.text}"
            )
        return response.json()
