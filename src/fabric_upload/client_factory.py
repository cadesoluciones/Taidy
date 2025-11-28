"""Helpers to build Fabric OneLake Data Lake clients."""

from urllib.parse import quote
from typing import Any

from .config import FabricUploadSettings


def create_file_system_client(settings: FabricUploadSettings) -> Any:
    """Return a Data Lake file system client for the Fabric lakehouse."""
    from azure.identity import ClientSecretCredential
    from azure.storage.filedatalake import DataLakeServiceClient

    credential = ClientSecretCredential(
        tenant_id=settings.tenant_id,
        client_id=settings.client_id,
        client_secret=settings.client_secret,
    )
    service_client = DataLakeServiceClient(
        account_url=_account_url(settings),
        credential=credential,
    )
    return service_client.get_file_system_client("Files")


def _account_url(settings: FabricUploadSettings) -> str:
    base = "https://onelake.dfs.fabric.microsoft.com"
    workspace_value = settings.workspace_name or settings.workspace_id
    lakehouse_value = settings.lakehouse_name or settings.lakehouse_id
    if not workspace_value or not lakehouse_value:
        raise ValueError(
            "Fabric workspace/lakehouse names or IDs must be configured for checkpoints"
        )
    workspace_segment = quote(workspace_value)
    lakehouse_segment = f"{quote(lakehouse_value)}.Lakehouse"
    return f"{base}/{workspace_segment}/{lakehouse_segment}"
