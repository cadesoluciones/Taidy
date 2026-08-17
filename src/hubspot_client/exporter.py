# -*- coding: utf-8 -*-
"""
Export helpers for HubSpot data.

Full extraction only (no incremental mode yet): every run overwrites
output_dir/full/<table>.csv, the same folder layout the BC FabricUploader
already expects.
"""

from pathlib import Path
from typing import Any, Dict, List

from src.bc_client.exporter import export_table

_FULL_DIR = "full"


def export_full(table_name: str, rows: List[Dict[str, Any]], output_dir: Path) -> None:
    full_dir = output_dir / _FULL_DIR
    full_dir.mkdir(parents=True, exist_ok=True)
    export_table(table_name, rows, full_dir)
