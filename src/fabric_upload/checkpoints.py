# -*- coding: utf-8 -*-
"""
Manages incremental ingestion checkpoints by storing them as JSON files in
Microsoft Fabric OneLake.

This module provides a `FabricCheckpointStore` class that abstracts the reading,
writing, and deleting of watermark files, allowing the rest of the application
to easily track the state of incremental data extractions.
"""

# --------------------------------------------------------------------------------------
# Imports
# --------------------------------------------------------------------------------------

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any, Optional

from azure.core.exceptions import HttpResponseError, ResourceNotFoundError

from .client_factory import create_file_system_client
from .config import FabricUploadSettings
from ..utils import get_logger, table_filename

# --------------------------------------------------------------------------------------
# Constants and Global Variables
# --------------------------------------------------------------------------------------

logger = get_logger(__name__)


# --------------------------------------------------------------------------------------
# Data Models
# --------------------------------------------------------------------------------------


@dataclass
class TableCheckpoint:
    """
    Represents the state of the last successful incremental extraction for a table.
    """

    table_name: str
    watermark_value: Optional[str]
    updated_at: datetime


# --------------------------------------------------------------------------------------
# Core Checkpoint Logic
# --------------------------------------------------------------------------------------


class FabricCheckpointStore:
    """
    Reads and writes checkpoint JSON files directly in a Fabric OneLake filesystem.

    This class handles all interactions with the remote checkpoint files, including
    path generation, file I/O, and serialization/deserialization of checkpoint data.
    """

    def __init__(
        self,
        settings: FabricUploadSettings,
        *,
        file_system_client: Optional[Any] = None,
        now_fn=None,
    ) -> None:
        """
        Initializes the checkpoint store.

        Args:
            settings: The Fabric upload settings, containing configuration for
                      connecting to OneLake.
            file_system_client: An optional pre-configured Azure DataLake file
                                system client, for testing.
            now_fn: An optional function to get the current time, for testing.
        """
        self._settings = settings
        self._file_system = file_system_client or create_file_system_client(settings)
        self._now = now_fn or (lambda: datetime.now(timezone.utc))
        self._checkpoint_root = settings.checkpoint_root

    def load(self, table_name: str) -> Optional[TableCheckpoint]:
        """
        Returns the stored checkpoint for a given table, if one exists.

        It constructs the remote path, attempts to download the file, and parses
        it into a `TableCheckpoint` object.

        Args:
            table_name: The name of the table to load the checkpoint for.

        Returns:
            A `TableCheckpoint` object if a valid checkpoint file is found,
            otherwise `None`.
        """
        path = self._remote_path(table_name)
        file_client = self._file_system.get_file_client(path.as_posix())

        try:
            data = file_client.download_file().readall()
        except ResourceNotFoundError:
            # This is an expected case for the first run of a table.
            logger.debug("No checkpoint found for table '%s'", table_name)
            return None
        except HttpResponseError as exc:
            # Any other HTTP error is unexpected and should be logged.
            logger.warning(
                "Failed to download checkpoint for '%s': %s", table_name, exc
            )
            raise

        try:
            payload = json.loads(data)
        except ValueError as exc:
            raise ValueError(
                f"Invalid JSON in checkpoint for table '{table_name}'"
            ) from exc

        return TableCheckpoint(
            table_name=table_name,
            watermark_value=_as_optional_str(payload.get("watermark_value")),
            updated_at=_parse_timestamp(payload.get("updated_at")),
        )

    def save(
        self,
        table_name: str,
        watermark_value: Optional[str],
        *,
        watermark_column: Optional[str] = None,
    ) -> TableCheckpoint:
        """
        Persists the latest watermark for the given table to a JSON file in OneLake.

        Args:
            table_name: The name of the table.
            watermark_value: The new watermark value to save (e.g., the max
                             `SystemModifiedAt` from the latest run).
            watermark_column: The name of the column used for the watermark.

        Returns:
            A `TableCheckpoint` object representing the state that was just saved.
        """
        timestamp = self._now()
        payload = {
            "table": table_name,
            "watermark_value": watermark_value,
            "watermark_column": watermark_column,
            "updated_at": timestamp.isoformat(),
        }

        path = self._remote_path(table_name)
        # Ensure the parent directory exists before trying to upload the file.
        self._ensure_remote_parent(path)

        file_client = self._file_system.get_file_client(path.as_posix())
        file_client.upload_data(json.dumps(payload).encode("utf-8"), overwrite=True)

        logger.debug(
            "Checkpoint saved for table '%s' at '%s' with watermark '%s'",
            table_name,
            path,
            watermark_value,
        )
        return TableCheckpoint(
            table_name=table_name,
            watermark_value=watermark_value,
            updated_at=timestamp,
        )

    def delete(self, table_name: str) -> None:
        """
        Removes a checkpoint file to force a full reload of the table on the next run.

        If the file does not exist, this operation does nothing.
        """
        path = self._remote_path(table_name)
        file_client = self._file_system.get_file_client(path.as_posix())
        try:
            file_client.delete_file()
            logger.info("Deleted checkpoint for table '%s'", table_name)
        except ResourceNotFoundError:
            # It's safe to ignore if the file is already gone.
            logger.debug(
                "Checkpoint file for table '%s' was already absent", table_name
            )

    def _remote_path(self, table_name: str) -> PurePosixPath:
        """
        Constructs the full remote path for a table's checkpoint file.

        Example: `raw/checkpoints/business_central/my_table.json`
        """
        return self._checkpoint_root / table_filename(table_name, suffix=".json")

    def _ensure_remote_parent(self, remote_path: PurePosixPath) -> None:
        """
        Creates the parent directory for a remote path if it doesn't exist.
        This is a "best-effort" operation.
        """
        parent = remote_path.parent
        # If the parent is the root ('.') or empty, there's nothing to create.
        if str(parent) in {"", "."}:
            return
        try:
            self._file_system.create_directory(str(parent))
        except Exception:  # pragma: no cover
            # Fail silently on directory creation, as the subsequent file upload
            # might create it anyway, or another process might be creating it.
            logger.debug(
                "Failed to create checkpoint directory '%s'", parent, exc_info=True
            )


# --------------------------------------------------------------------------------------
# Internal Helper Functions
# --------------------------------------------------------------------------------------


def _parse_timestamp(raw: Optional[str]) -> datetime:
    """
    Safely parses an ISO 8601 timestamp string into a timezone-aware datetime.

    It handles timestamps ending in 'Z' and defaults to the epoch if the
    timestamp is missing or invalid.
    """
    if not raw:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    try:
        # The 'Z' suffix for UTC is not directly supported by fromisoformat,
        # so we replace it with the equivalent '+00:00'.
        normalized = raw.replace("Z", "+00:00") if raw.endswith("Z") else raw
        return datetime.fromisoformat(normalized)
    except ValueError:
        # If parsing fails, log it and return a default value to avoid crashing.
        logger.debug("Failed to parse checkpoint timestamp '%s'", raw, exc_info=True)
        return datetime.fromtimestamp(0, tz=timezone.utc)


def _as_optional_str(value: Any) -> Optional[str]:
    """
    Safely casts a value to an optional string.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        return str(value)
    return value
