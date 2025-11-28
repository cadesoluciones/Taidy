"""Fabric-backed checkpoint storage for incremental ingestion."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any, Optional

from azure.core.exceptions import HttpResponseError, ResourceNotFoundError

from .client_factory import create_file_system_client
from .config import FabricUploadSettings
from ..utils import get_logger

logger = get_logger(__name__)


@dataclass
class TableCheckpoint:
    table_name: str
    watermark_value: Optional[str]
    updated_at: datetime


class FabricCheckpointStore:
    """Read and write checkpoint JSON files directly in OneLake."""

    def __init__(
        self,
        settings: FabricUploadSettings,
        *,
        file_system_client: Optional[Any] = None,
        now_fn: Optional[Any] = None,
    ) -> None:
        self._settings = settings
        self._file_system = file_system_client or create_file_system_client(settings)
        self._now = now_fn or (lambda: datetime.now(timezone.utc))

    def load(self, table_name: str) -> Optional[TableCheckpoint]:
        """Return the stored checkpoint for the table, if present."""
        path = self._remote_path(table_name)
        file_client = self._file_system.get_file_client(path)
        try:
            data = file_client.download_file().readall()
        except ResourceNotFoundError:
            logger.debug("No checkpoint found for table '%s'", table_name)
            return None
        except HttpResponseError as exc:
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
        """Persist the latest watermark for the given table."""
        timestamp = self._now()
        payload = {
            "table": table_name,
            "watermark_value": watermark_value,
            "watermark_column": watermark_column,
            "updated_at": timestamp.isoformat(),
        }

        path = self._remote_path(table_name)
        self._ensure_remote_parent(path)
        file_client = self._file_system.get_file_client(path)
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
        """Remove the checkpoint file to force a full reload."""
        path = self._remote_path(table_name)
        file_client = self._file_system.get_file_client(path)
        try:
            file_client.delete_file()
            logger.info("Deleted checkpoint for table '%s'", table_name)
        except ResourceNotFoundError:
            logger.debug(
                "Checkpoint file for table '%s' was already absent", table_name
            )

    def _remote_path(self, table_name: str) -> str:
        root = PurePosixPath(self._settings.checkpoint_path)
        return (root / f"{self._sanitize_table(table_name)}.json").as_posix()

    def _ensure_remote_parent(self, remote_path: str) -> None:
        parent = PurePosixPath(remote_path).parent
        if str(parent) in {"", "."}:
            return
        try:
            self._file_system.create_directory(parent.as_posix(), exist_ok=True)
        except Exception:  # pragma: no cover - best effort
            logger.debug(
                "Failed to create checkpoint directory '%s'", parent, exc_info=True
            )

    @staticmethod
    def _sanitize_table(raw: str) -> str:
        cleaned = raw.strip().lower().replace(" ", "_")
        cleaned = "".join(ch for ch in cleaned if ch.isalnum() or ch in {"-", "_"})
        cleaned = cleaned.strip("_-")
        if not cleaned:
            raise ValueError("Table name must include alphanumeric characters")
        return cleaned


def _parse_timestamp(raw: Optional[str]) -> datetime:
    if not raw:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    try:
        # Allow timestamps saved with trailing Z
        normalized = raw.replace("Z", "+00:00") if raw.endswith("Z") else raw
        return datetime.fromisoformat(normalized)
    except ValueError:
        logger.debug("Failed to parse checkpoint timestamp '%s'", raw, exc_info=True)
        return datetime.fromtimestamp(0, tz=timezone.utc)


def _as_optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        return str(value)
    return value
