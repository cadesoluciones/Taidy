# -*- coding: utf-8 -*-
"""
Main entry point for the HubSpot CRM data extraction command-line tool.

Full extraction only: parses CLI arguments, loads settings, calls the
HubSpot CRM v3 Objects API (with cursor pagination), and writes CSV files.
Unlike Factorial there is no date range, employee filter, or checkpoint
based incremental mode yet.
"""

import argparse
import logging
import os
import signal
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from dotenv import load_dotenv

from src.hubspot_client.config import Settings, TableConfig, load_settings
from src.hubspot_client.exporter import export_full
from src.utils import (
    coerce_dir,
    configure_logging as configure_rich_logging,
    get_logger,
)
from src.hubspot_client.api import HubspotClient

# --------------------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------------------

logger = get_logger(__name__)

DEFAULT_OUTPUT_DIR = "./exports_hubspot"


# --------------------------------------------------------------------------------------
# CLI Argument Parsing
# --------------------------------------------------------------------------------------


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download HubSpot CRM objects to CSV")

    parser.add_argument(
        "--tables",
        nargs="*",
        help=(
            "Override table list (names as defined in hubspot_tables.yaml, "
            "e.g. --tables hubspot_contacts)"
        ),
    )
    parser.add_argument("--output-dir", help="Override CSV output directory")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log planned actions without calling the API",
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=1,
        help="Number of tables to extract concurrently (default: 1)",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")

    return parser.parse_args(list(argv) if argv is not None else None)


# --------------------------------------------------------------------------------------
# Configuration helpers
# --------------------------------------------------------------------------------------


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    configure_rich_logging(level)


def apply_overrides(settings: Settings, args: argparse.Namespace) -> Settings:
    tables = _override_tables(settings.tables, args.tables)
    output_dir = _override_output_dir(settings.output_dir, args.output_dir)
    return replace(settings, tables=tables, output_dir=output_dir)


def _override_tables(
    configured: List[TableConfig],
    requested_names: Optional[List[str]],
) -> List[TableConfig]:
    if not requested_names:
        return list(configured)

    requested = [n for n in requested_names if n]
    if not requested:
        raise ValueError("At least one table name must be provided with --tables")

    table_map = {t.name: t for t in configured}
    missing = [n for n in requested if n not in table_map]
    if missing:
        raise ValueError(f"Unknown table(s) requested: {', '.join(missing)}")

    return [table_map[n] for n in requested]


def _override_output_dir(configured: Path, override: Optional[str]) -> Path:
    if not override:
        return configured
    return coerce_dir(override)


# --------------------------------------------------------------------------------------
# Core extraction
# --------------------------------------------------------------------------------------


def _run_extractions(
    *,
    tables: List[TableConfig],
    client: HubspotClient,
    output_dir: Path,
    parallel_workers: int,
) -> int:
    def _fetch_and_export(table: TableConfig) -> Tuple[str, bool]:
        rows = client.fetch_table(table)
        export_full(table.name, rows, output_dir)
        return table.name, True

    if parallel_workers <= 1:
        written = 0
        for table in tables:
            _fetch_and_export(table)
            written += 1
        return written

    logger.info("Running extractions with up to %d parallel workers.", parallel_workers)
    written = 0
    executor = ThreadPoolExecutor(max_workers=parallel_workers)
    futures = {executor.submit(_fetch_and_export, t): t for t in tables}
    try:
        for future in as_completed(futures):
            table_name, _ = future.result()
            logger.info("Completed '%s'.", table_name)
            written += 1
    except KeyboardInterrupt:
        logger.warning("Interrupted — cancelling pending tasks...")
        for f in futures:
            f.cancel()
        raise
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    return written


def _log_summary(*, tables: int, written: int, output: Path) -> None:
    skipped = tables - written
    logger.info(
        "\n========== HubSpot Extract =========="
        "\nTables processed : %d"
        "\nNew files        : %d"
        "\nTables skipped   : %d"
        "\nOutput folder    : %s"
        "\n=======================================",
        tables,
        written,
        skipped,
        output,
    )


def run_extract(argv: Optional[Iterable[str]] = None) -> tuple[int, Optional[Path]]:
    args = parse_args(argv)
    configure_logging(args.verbose)

    try:
        load_dotenv()
        settings = load_settings()
        settings = apply_overrides(settings, args)

        output_dir = settings.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        tables = settings.tables

        logger.info("HubSpot extract: %d table(s).", len(tables))
        logger.info("Writing CSVs to %s", output_dir)

        if args.dry_run:
            for table in tables:
                dest = output_dir / f"{table.name}.csv"
                logger.info("[dry-run] Would write '%s' → %s", table.name, dest)
            _log_summary(tables=len(tables), written=0, output=output_dir)
            return 0, output_dir

        parallel_workers = args.parallel
        if parallel_workers <= 0:
            raise ValueError("--parallel must be greater than zero")

        client = HubspotClient(settings=settings)
        written = _run_extractions(
            tables=tables,
            client=client,
            output_dir=output_dir,
            parallel_workers=parallel_workers,
        )

        _log_summary(tables=len(tables), written=written, output=output_dir)
        return 0, output_dir

    except KeyboardInterrupt:
        logger.warning("Extraction interrupted by user.")
        return 130, None
    except Exception as exc:
        logger.exception("Failed to extract HubSpot data: %s", exc)
        return 1, None


# --------------------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------------------


def main() -> None:
    signal.signal(signal.SIGINT, lambda *_: os._exit(130))
    status, _ = run_extract()
    sys.exit(status)


if __name__ == "__main__":
    main()
