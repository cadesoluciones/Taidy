"""CSV export helpers."""

import csv
import logging
import re
from pathlib import Path
from typing import Iterable, Mapping

logger = logging.getLogger(__name__)


def _sanitize_table_name(table_name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", table_name.strip().lower()).strip("_")
    if not cleaned:
        cleaned = "table"
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
    logger.info(
        "Table '%s' export complete; %s rows written to '%s'",
        table_name,
        row_count,
        destination,
    )
    return destination
