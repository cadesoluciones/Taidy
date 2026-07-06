# -*- coding: utf-8 -*-
"""
Local checkpoint store for Factorial incremental extractions.

Checkpoints are stored as JSON files under:
    <output_dir>/.checkpoints/<table_name>.json
"""

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from ..utils import get_logger

logger = get_logger(__name__)

_CHECKPOINT_DIR = ".checkpoints"


def checkpoint_dir(output_dir: Path) -> Path:
    return output_dir / _CHECKPOINT_DIR


def load(table_name: str, output_dir: Path) -> Optional[date]:
    """Returns the last saved end_on date for the table, or None if not found."""
    path = checkpoint_dir(output_dir) / f"{table_name}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return date.fromisoformat(data["last_end_on"])
    except Exception as exc:
        logger.warning("Could not read checkpoint for '%s': %s", table_name, exc)
        return None


def save(table_name: str, end_on: date, output_dir: Path) -> None:
    """Persists end_on as the checkpoint for the table."""
    dir_ = checkpoint_dir(output_dir)
    dir_.mkdir(parents=True, exist_ok=True)
    path = dir_ / f"{table_name}.json"
    path.write_text(
        json.dumps({"last_end_on": end_on.isoformat()}, indent=2),
        encoding="utf-8",
    )
    logger.debug("Checkpoint saved for '%s': %s", table_name, end_on)


def reset(table_name: str, output_dir: Path) -> None:
    """Deletes the checkpoint for a single table."""
    path = checkpoint_dir(output_dir) / f"{table_name}.json"
    if path.exists():
        path.unlink()
        logger.info("Checkpoint reset for '%s'.", table_name)


def reset_all(output_dir: Path) -> None:
    """Deletes all checkpoints."""
    dir_ = checkpoint_dir(output_dir)
    if dir_.exists():
        for f in dir_.glob("*.json"):
            f.unlink()
        logger.info("All checkpoints reset.")


def resolve_start_on(
    table_name: str,
    fallback_start: date,
    output_dir: Path,
    overlap_days: int,
) -> date:
    """
    Returns the effective start date for an incremental run.

    If a checkpoint exists: last_end_on - overlap_days.
    Otherwise falls back to the CLI --start-on value.
    """
    last = load(table_name, output_dir)
    if last is None:
        logger.info(
            "'%s': no checkpoint found, using --start-on %s.", table_name, fallback_start
        )
        return fallback_start

    effective = last - timedelta(days=overlap_days)
    logger.info(
        "'%s': checkpoint=%s, overlap=%d days → start_on=%s.",
        table_name,
        last,
        overlap_days,
        effective,
    )
    return effective
