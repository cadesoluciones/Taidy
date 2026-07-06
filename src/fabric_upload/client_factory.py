# -*- coding: utf-8 -*-
"""
Factory functions for creating Azure Data Lake service clients for Fabric OneLake.

This module encapsulates the logic for instantiating the Azure SDK clients needed
to interact with the OneLake file system. It centralizes the construction of
account URLs and credential objects, simplifying client creation in other parts
of the application.
"""

# --------------------------------------------------------------------------------------
# Imports
# --------------------------------------------------------------------------------------

from typing import Any
from urllib.parse import quote

from .config import FabricUploadSettings

# --------------------------------------------------------------------------------------
# Public Functions
# --------------------------------------------------------------------------------------


def create_file_system_client(settings: FabricUploadSettings) -> Any:
    """
    Creates and returns a Data Lake file system client for the Fabric lakehouse.

    This function uses the provided settings to authenticate with Azure via
    client credentials and then constructs a service client pointed at the
    correct OneLake account URL. It specifically targets the "Files" filesystem
    within the specified Lakehouse.

    Args:
        settings: The Fabric upload settings containing credentials and endpoint
                  details.

    Returns:
        An instance of `FileSystemClient` from the Azure SDK, ready to be used
        for file operations. The return type is `Any` to avoid a hard dependency
        on `azure-storage-file-datalake` for consumers of this module who may
        not need the client directly.
    """
    # Import is done locally to avoid making `azure-identity` and
    # `azure-storage-file-datalake` hard dependencies for modules that
    # might just import types.
    from azure.identity import ClientSecretCredential
    from azure.storage.filedatalake import DataLakeServiceClient

    # Authenticate using client ID and secret.
    credential = ClientSecretCredential(
        tenant_id=settings.tenant_id,
        client_id=settings.client_id,
        client_secret=settings.client_secret,
    )

    # Create the top-level service client pointing to the OneLake account.
    service_client = DataLakeServiceClient(
        account_url=_account_url(settings),
        credential=credential,
    )

    # Return a client scoped to the "Files" filesystem within the Lakehouse,
    # which is the standard location for user-managed files.
    return service_client.get_file_system_client("Files")


# --------------------------------------------------------------------------------------
# Internal Helper Functions
# --------------------------------------------------------------------------------------


def _account_url(settings: FabricUploadSettings) -> str:
    """
    Constructs the specific OneLake account URL for a given workspace and lakehouse.

    The URL format is `https://onelake.dfs.fabric.microsoft.com/{Workspace}/{Lakehouse}.Lakehouse`.
    It prioritizes using the workspace/lakehouse name if available, as they are
    more human-readable than the GUID-based IDs.

    Args:
        settings: The Fabric upload settings.

    Raises:
        ValueError: If neither a name nor an ID is provided for the workspace
                    or lakehouse.

    Returns:
        The fully-qualified OneLake account URL.
    """

    base = "https://onelake.dfs.fabric.microsoft.com"

    # Use the friendly name if available, otherwise fall back to the GUID.
    workspace_value = settings.workspace_name or settings.workspace_id
    lakehouse_value = settings.lakehouse_name or settings.lakehouse_id

    if not workspace_value or not lakehouse_value:
        raise ValueError(
            "Fabric workspace/lakehouse names or IDs must be configured to build the OneLake URL."
        )

    # URL-encode the workspace and lakehouse names to handle spaces and special chars.
    workspace_segment = quote(workspace_value)
    # The lakehouse segment must end with the `.Lakehouse` suffix.
    lakehouse_segment = f"{quote(lakehouse_value)}.Lakehouse"

    return f"{base}/{workspace_segment}/{lakehouse_segment}"
