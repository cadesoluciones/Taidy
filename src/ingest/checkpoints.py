"""Helpers for building and managing Fabric checkpoint stores."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from src.bc_client.config import TableConfig
from src.fabric_upload.checkpoints import FabricCheckpointStore
from src.fabric_upload.config import load_fabric_settings
from src.ingest.jobs import supports_incremental


def build_checkpoint_store(
    tables: List[TableConfig],
    output_dir: Path,
    checkpoint_path_override: Optional[str] = None,
) -> Optional[FabricCheckpointStore]:
    """Return a FabricCheckpointStore when any table requires incremental mode."""
    if not any(supports_incremental(table) for table in tables):
        return None

    fabric_settings = load_fabric_settings(
        output_dir,
        force_enable=True,
        checkpoint_path_override=checkpoint_path_override,
    )
    if fabric_settings is None:
        raise RuntimeError("Fabric uploads must be enabled for incremental tables")
    return FabricCheckpointStore(fabric_settings)


def reset_checkpoints(
    store: FabricCheckpointStore,
    tables: List[TableConfig],
) -> None:
    """Delete stored watermarks for the provided tables."""
    for table in tables:
        if supports_incremental(table):
            store.delete(table.name)
