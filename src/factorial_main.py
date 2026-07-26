# -*- coding: utf-8 -*-
"""
Main entry point for the Factorial HR data extraction command-line tool.

Orchestrates the full extraction: parses CLI arguments, loads settings,
calls the Factorial API (with cursor pagination), and writes CSV files.
"""

import argparse
import logging
import os
import signal
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from dotenv import load_dotenv

from src.factorial_client.config import Settings, TableConfig, load_settings
from src.factorial_client.exporter import export_full, export_incremental
from src.utils import (
    coerce_dir,
    configure_logging as configure_rich_logging,
    get_logger,
)
from src.factorial_client.api import FactorialClient
from src.factorial_client import checkpoints

# --------------------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------------------

logger = get_logger(__name__)

DEFAULT_OUTPUT_DIR = "./exports_factorial"


# --------------------------------------------------------------------------------------
# CLI Argument Parsing
# --------------------------------------------------------------------------------------


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Factorial HR tables to CSV"
    )

    # --- Required date range ---
    parser.add_argument(
        "--start-on",
        required=True,
        metavar="YYYY-MM-DD",
        help="Start date for the extraction range (inclusive)",
    )
    parser.add_argument(
        "--end-on",
        required=True,
        metavar="YYYY-MM-DD",
        help="End date for the extraction range (inclusive)",
    )

    # --- Employees ---
    parser.add_argument(
        "--employees",
        nargs="+",
        type=int,
        default=None,
        metavar="ID",
        help=(
            "Factorial employee IDs to extract (e.g. --employees 1184502 1269520). "
            "If omitted, IDs are auto-discovered from the factorial_employees table."
        ),
    )
    parser.add_argument(
        "--employee-status",
        choices=("active", "inactive", "all"),
        default="active",
        help=(
            "Filter employees when auto-discovering: "
            "'active' (default), 'inactive', or 'all'."
        ),
    )

    # --- Optional overrides ---
    parser.add_argument(
        "--tables",
        nargs="*",
        help=(
            "Override table list (names as defined in factorial_tables.yaml, "
            "e.g. --tables factorial_estimated_times)"
        ),
    )
    parser.add_argument("--output-dir", help="Override CSV output directory")

    # --- Execution modes ---
    parser.add_argument(
        "--mode",
        choices=("full", "incremental"),
        default="full",
        help=(
            "Extraction mode: 'full' (default) uses --start-on as-is; "
            "'incremental' resumes from the last saved checkpoint (minus overlap days)."
        ),
    )
    parser.add_argument(
        "--reset-checkpoints",
        nargs="*",
        metavar="TABLE",
        help=(
            "Reset checkpoints before extracting. "
            "Pass table names to reset specific ones, or no names to reset all."
        ),
    )
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
# Summary
# --------------------------------------------------------------------------------------


def _resolve_employee_ids(
    client: FactorialClient,
    settings,
    employee_status: str,
) -> List[int]:
    """Fetches employee IDs from factorial_employees, filtered by status."""
    emp_table = next(
        (t for t in settings.tables if t.name == "factorial_employees"), None
    )
    if emp_table is None:
        raise ValueError(
            "No 'factorial_employees' table found in factorial_tables.yaml — "
            "required for auto-discovery. Add it or use --employees explicitly."
        )

    extra: List = []
    if employee_status == "active":
        extra = [("only_active", "true")]
    elif employee_status == "inactive":
        extra = [("only_active", "false")]

    rows = client.fetch_table(emp_table, extra_params=extra)
    ids = [r["id"] for r in rows if r.get("id") is not None]

    if not ids:
        raise ValueError(
            f"Auto-discovery returned 0 employees (status='{employee_status}'). "
            "Check your API key or use --employees explicitly."
        )

    logger.info(
        "Auto-discovered %d employee(s) (status=%s).", len(ids), employee_status
    )
    return ids


def _run_extractions(
    *,
    tables,
    client: FactorialClient,
    output_dir: Path,
    start_on: str,
    end_on: str,
    employee_ids: List[int],
    employee_status: str,
    parallel_workers: int,
    mode: str,
    overlap_days: int,
) -> int:
    end_date = date.fromisoformat(end_on)
    fallback_start = date.fromisoformat(start_on)
    run_ts = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")

    def _extra_params_for(table) -> Optional[List]:
        return None

    def _effective_start(table) -> str:
        if mode == "incremental" and table.incremental:
            effective_overlap = table.overlap_days if table.overlap_days is not None else overlap_days
            return checkpoints.resolve_start_on(
                table.name, fallback_start, output_dir, effective_overlap
            ).isoformat()
        return start_on

    def _fetch_and_export(table) -> Tuple[str, bool]:
        effective = _effective_start(table)
        rows = client.fetch_table(
            table,
            start_on=effective,
            end_on=end_on,
            employee_ids=employee_ids,
            extra_params=_extra_params_for(table),
        )
        if mode == "incremental" and table.incremental:
            export_incremental(table.name, rows, output_dir, run_ts)
            checkpoints.save(table.name, end_date, output_dir)
        else:
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
        "\n========== Factorial Extract =========="
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


# --------------------------------------------------------------------------------------
# Core extraction
# --------------------------------------------------------------------------------------


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
        start_on: str = args.start_on
        end_on: str = args.end_on

        # Validate dates
        date.fromisoformat(start_on)
        date.fromisoformat(end_on)

        # Handle checkpoint resets before extraction
        if args.reset_checkpoints is not None:
            if args.reset_checkpoints:
                for name in args.reset_checkpoints:
                    checkpoints.reset(name, output_dir)
            else:
                checkpoints.reset_all(output_dir)

        client = FactorialClient(settings=settings)

        # Resolve employee IDs only if at least one table needs them
        needs_employees = any(t.employee_filter for t in tables)

        if args.employees:
            employee_ids: List[int] = args.employees
            logger.info("Using %d explicit employee(s).", len(employee_ids))
        elif needs_employees:
            employee_ids = _resolve_employee_ids(
                client, settings, args.employee_status
            )
        else:
            employee_ids = []

        logger.info(
            "Factorial extract: %d table(s), %s → %s, employees=%d (%s), mode=%s",
            len(tables),
            start_on,
            end_on,
            len(employee_ids),
            args.employee_status if not args.employees else "explicit",
            args.mode,
        )
        logger.info("Writing CSVs to %s", output_dir)

        if args.dry_run:
            for table in tables:
                dest = output_dir / f"{table.name}.csv"
                if args.mode == "incremental" and table.incremental:
                    effective_overlap = table.overlap_days if table.overlap_days is not None else settings.overlap_days
                    effective = checkpoints.resolve_start_on(
                        table.name, date.fromisoformat(start_on), output_dir, effective_overlap
                    ).isoformat()
                    logger.info(
                        "[dry-run] Would write '%s' → %s (incremental, start=%s)",
                        table.name, dest, effective,
                    )
                else:
                    logger.info("[dry-run] Would write '%s' → %s", table.name, dest)
            _log_summary(tables=len(tables), written=0, output=output_dir)
            return 0, output_dir

        parallel_workers = args.parallel
        if parallel_workers <= 0:
            raise ValueError("--parallel must be greater than zero")

        written = _run_extractions(
            tables=tables,
            client=client,
            output_dir=output_dir,
            start_on=start_on,
            end_on=end_on,
            employee_ids=employee_ids,
            employee_status=args.employee_status,
            parallel_workers=parallel_workers,
            mode=args.mode,
            overlap_days=settings.overlap_days,
        )

        _log_summary(tables=len(tables), written=written, output=output_dir)
        return 0, output_dir

    except KeyboardInterrupt:
        logger.warning("Extraction interrupted by user.")
        return 130, None
    except Exception as exc:
        logger.exception("Failed to extract Factorial data: %s", exc)
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
