# -*- coding: utf-8 -*-
"""
CSV export helpers for writing Business Central data to the local filesystem.

This module provides an "atomic" export function that writes data to a temporary
file and then renames it to the final destination upon successful completion.
This prevents partial or corrupt files in case of an error during the export
process. It also includes utilities for sanitizing table names into valid
filenames.
"""

# --------------------------------------------------------------------------------------
# Imports
# --------------------------------------------------------------------------------------

import csv
import re
from pathlib import Path
from typing import Iterable, Mapping

from ..utils import get_logger

# --------------------------------------------------------------------------------------
# Constants and Global Variables
# --------------------------------------------------------------------------------------

logger = get_logger(__name__)


# --------------------------------------------------------------------------------------
# Internal Helper Functions
# --------------------------------------------------------------------------------------


def _sanitize_table_name(table_name: str) -> str:
    """
    Cleans a table name to create a safe, valid filename.

    The process involves:
    1. Converting the name to lowercase.
    2. Replacing any character that is not a letter, number, underscore, or
       hyphen with an underscore.
    3. Stripping leading/trailing underscores.
    4. Appending the `.csv` extension.

    Args:
        table_name: The raw table name (e.g., "My/Table Name").

    Raises:
        ValueError: If the table name is empty or results in an empty/invalid
                    cleaned name.

    Returns:
        A sanitized, file-safe name ending in `.csv` (e.g., "my_table_name.csv").
    """
    if not table_name or not isinstance(table_name, str):
        raise ValueError("Table name must be a non-empty string")

    # This regex replaces any character that is NOT in the allowed set [a-z0-9_-]
    # with an underscore.
    cleaned = re.sub(r"[^a-z0-9_-]", "_", table_name.strip().lower()).strip("_")

    # Final validation to ensure the cleaned name is usable.
    if not cleaned or len(cleaned) > 255:
        raise ValueError(f"Invalid table name: {table_name}")

    return f"{cleaned}.csv"


# --------------------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------------------


def export_table(
    table_name: str, rows: Iterable[Mapping[str, object]], output_dir: Path
) -> Path:
    """
    Exports an iterable of data rows to a CSV file atomically.

    This function streams the `rows` iterable to a temporary CSV file. Once all
    rows are written, it renames the temporary file to its final destination.
    This ensures that the final CSV file is only created if the entire export
    is successful, preventing partial writes.

    If the `rows` iterable is empty, an empty CSV file is created with no header.

    Args:
        table_name: The name of the table, used to generate the filename.
        rows: An iterable of dictionaries, where each dictionary is a row.
        output_dir: The directory where the final CSV file will be saved.

    Raises:
        RuntimeError: If an `OSError` or `csv.Error` occurs during file writing.
        ValueError: If the rows are not mappings (dictionaries).

    Returns:
        The `Path` to the newly created CSV file.
    """
    logger.info("Preparing export for table '%s' into '%s'", table_name, output_dir)
    # Ensure the target directory exists before starting.
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.debug("Ensured output directory exists")

    # Sanitize the table name and determine final and temporary file paths.
    filename = _sanitize_table_name(table_name)
    destination = output_dir / filename

    # The iterator is explicitly created to peek at the first row.
    iterator = iter(rows)
    try:
        first_row = next(iterator)
    except StopIteration:
        # Handle the edge case of an empty dataset.
        logger.info(
            "Table '%s' returned no rows; creating empty file '%s'",
            table_name,
            destination,
        )
        # Create an empty file and return early.
        destination.open("w", newline="", encoding="utf-8").close()
        return destination

    # The keys of the first row determine the CSV header.
    if not isinstance(first_row, Mapping):
        raise ValueError("Rows must be mappings (e.g., dictionaries)")

    fieldnames = [str(name) for name in first_row.keys()]
    # Use a hidden temporary file in the same directory to ensure atomic rename.
    temp_path = output_dir / f".{filename}.tmp"

    try:
        # Write to the temporary file first.
        with temp_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()

            # Write the first row that was already peeked.
            writer.writerow(first_row)
            row_count = 1
            logger.debug(
                "Writing export header for table '%s': %s", table_name, fieldnames
            )

            # Iterate through the rest of the rows.
            for row in iterator:
                if not isinstance(row, Mapping):
                    raise ValueError("Rows must be mappings")
                writer.writerow(row)
                row_count += 1

        # Atomically move the temporary file to the final destination.
        # This is the key step for preventing partial files.
        temp_path.replace(destination)

    except (OSError, csv.Error) as exc:
        # Cleanup: If the export fails, delete the temporary file.
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
