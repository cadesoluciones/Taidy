"""CSV export helpers."""

import csv
import re
from pathlib import Path
from typing import Iterable, Mapping

from ..utils import get_logger

logger = get_logger(__name__)


def _sanitize_table_name(table_name: str) -> str:
    if not table_name or not isinstance(table_name, str):
        raise ValueError("Table name must be a non-empty string")
    cleaned = re.sub(r"[^a-z0-9_-]", "_", table_name.strip().lower()).strip("_")
    if not cleaned or len(cleaned) > 255:
        raise ValueError(f"Invalid table name: {table_name}")
    return f"{cleaned}.csv"


def export_table(
    table_name: str, rows: Iterable[Mapping[str, object]], output_dir: Path
) -> Path:
    logger.info("Preparing export for table '%s' into '%s'", table_name, output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.debug("Ensured output directory exists")

    filename = _sanitize_table_name(table_name)
    destination = output_dir / filename

    iterator = iter(rows)
    try:
        first_row = next(iterator)
    except StopIteration:
        logger.info(
            "Table '%s' returned no rows; creating empty file '%s'",
            table_name,
            destination,
        )
        destination.open("w", newline="", encoding="utf-8").close()
        return destination

    if not isinstance(first_row, Mapping):
        raise ValueError("Rows must be mappings")

    fieldnames = [str(name) for name in first_row.keys()]
    temp_path = output_dir / f".{filename}.tmp"

    try:
        with temp_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerow(first_row)
            row_count = 1
            logger.debug(
                "Writing export header for table '%s': %s (first row fields)",
                table_name,
                fieldnames,
            )
            for row in iterator:
                if not isinstance(row, Mapping):
                    raise ValueError("Rows must be mappings")
                writer.writerow(row)
                row_count += 1

        temp_path.replace(destination)
    except (OSError, csv.Error) as exc:
        if temp_path.exists():
            temp_path.unlink()
        raise RuntimeError(f"Failed to export table '{table_name}': {exc}") from exc
    logger.info(
        "Table '%s' export complete; %s rows written to '%s'",
        table_name,
        row_count,
        destination,
    )
    return destination
