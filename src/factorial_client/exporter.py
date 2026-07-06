# -*- coding: utf-8 -*-
"""
Export helpers for Factorial data.

All master (latest) CSVs land in output_dir/full/ so the BC FabricUploader
can pick them up using its expected folder layout.

- export_full: overwrites output_dir/full/<table>.csv
- export_incremental:
    1. Archives this run's rows to output_dir/incremental/<run_ts>/<table>.csv
    2. Merges into output_dir/full/<table>.csv, deduplicating by all fields.
       New rows win over existing ones when all fields match.
"""

import csv
from pathlib import Path
from typing import Any, Dict, List

from src.bc_client.exporter import export_table
from src.utils import get_logger

logger = get_logger(__name__)

_FULL_DIR = "full"


def export_full(table_name: str, rows: List[Dict[str, Any]], output_dir: Path) -> None:
    full_dir = output_dir / _FULL_DIR
    full_dir.mkdir(parents=True, exist_ok=True)
    export_table(table_name, rows, full_dir)


def export_incremental(
    table_name: str,
    rows: List[Dict[str, Any]],
    output_dir: Path,
    run_ts: str,
) -> None:
    run_dir = output_dir / "incremental" / run_ts
    run_dir.mkdir(parents=True, exist_ok=True)
    export_table(table_name, rows, run_dir)
    logger.info("'%s': run archived to %s", table_name, run_dir)

    if not rows:
        return
    _merge_into_master(table_name, rows, output_dir)


def _merge_into_master(
    table_name: str,
    new_rows: List[Dict[str, Any]],
    output_dir: Path,
) -> None:
    fieldnames = list(new_rows[0].keys())
    full_dir = output_dir / _FULL_DIR
    full_dir.mkdir(parents=True, exist_ok=True)
    master = full_dir / f"{table_name}.csv"

    existing: List[Dict[str, Any]] = []
    if master.exists():
        with master.open(encoding="utf-8", newline="") as f:
            existing = list(csv.DictReader(f))

    # New rows first so they win over identical keys in existing data
    seen: set = set()
    merged: List[Dict[str, Any]] = []
    for row in new_rows + existing:
        key = tuple(str(row.get(f, "")) for f in fieldnames)
        if key not in seen:
            seen.add(key)
            merged.append(row)

    tmp = master.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(merged)
    tmp.replace(master)

    added = len(merged) - len(existing)
    logger.info(
        "'%s': master updated → %d rows total (+%d new).",
        table_name, len(merged), max(added, 0),
    )
