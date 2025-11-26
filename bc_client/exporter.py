"""CSV export helpers."""

import csv
import re
from pathlib import Path
from typing import Iterable, Mapping


def _sanitize_table_name(table_name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", table_name.strip().lower()).strip("_")
    if not cleaned:
        cleaned = "table"
    return f"{cleaned}.csv"


def export_table(
    table_name: str, rows: Iterable[Mapping[str, object]], output_dir: Path
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = _sanitize_table_name(table_name)
    destination = output_dir / filename

    iterator = iter(rows)
    try:
        first_row = next(iterator)
    except StopIteration:
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
        for row in iterator:
            if not isinstance(row, Mapping):
                raise ValueError("Rows must be mappings")
            writer.writerow(row)

    temp_path.replace(destination)
    return destination
