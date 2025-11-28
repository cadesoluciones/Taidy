"""Entry point for the Business Central data extraction PoC.

Run this module as a script to download configured tables into CSV files. The
script expects configuration via environment variables (see `.env.example`) and
supports basic CLI overrides for ad-hoc experimentation.
"""

import argparse
import logging
import sys
from datetime import datetime, timezone
from dataclasses import replace
from pathlib import Path
from typing import Iterable, List, Optional

from dotenv import load_dotenv

from src.bc_client.config import DEFAULT_PAGE_SIZE, Settings, TableConfig, load_settings
from src.ingest.checkpoints import build_checkpoint_store, reset_checkpoints
from src.ingest.executor import log_dry_run, run_exports
from src.ingest.jobs import prepare_export_jobs
from src.utils import configure_logging as configure_rich_logging, get_logger


logger = get_logger(__name__)


# ---------------------------
# CLI / config
# ---------------------------


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Business Central tables to CSV"
    )
    parser.add_argument(
        "--tables",
        nargs="*",
        help="Override configured table list (pass table names as defined in tables.yaml, e.g., --tables bc_job_headers bc_job_planning_lines)",
    )
    parser.add_argument("--output-dir", help="Override CSV output directory")
    parser.add_argument(
        "--page-size",
        type=int,
        help=(
            "Override Business Central page size "
            f"(defaults to BC_PAGE_SIZE or {DEFAULT_PAGE_SIZE})"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log actions without calling the API",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--parallel",
        type=int,
        default=1,
        help="Number of tables to export concurrently (default: 1)",
    )
    parser.add_argument(
        "--mode",
        choices=("incremental", "full"),
        default="incremental",
        help=(
            "Choose incremental or full snapshot mode (incremental tables use SystemModifiedAt checkpoints; non-incremental tables always do full exports)."
        ),
    )
    parser.add_argument(
        "--reset-watermarks",
        action="store_true",
        help="Delete stored Fabric checkpoints before running (forces full reload for tables marked incremental)",
    )
    parser.add_argument(
        "--checkpoint-path",
        help="Override Fabric checkpoint path inside OneLake Files (default: raw/checkpoints/business_central)",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    configure_rich_logging(level)
    if not verbose:
        for name in ("azure", "azure.identity", "azure.core"):
            logging.getLogger(name).setLevel(logging.WARNING)


def apply_overrides(settings: Settings, args: argparse.Namespace) -> Settings:
    tables = _override_tables(settings.tables, args.tables)
    output_dir = _override_output_dir(settings.output_dir, args.output_dir)
    page_size = _override_page_size(settings.page_size, args.page_size)

    return replace(
        settings,
        tables=tables,
        output_dir=output_dir,
        page_size=page_size,
    )


def _override_tables(
    configured: List[TableConfig],
    requested_names: Optional[List[str]],
) -> List[TableConfig]:
    if not requested_names:
        return list(configured)

    requested = [name for name in requested_names if name]
    if not requested:
        raise ValueError("At least one table name must be provided with --tables")

    table_map = {t.name: t for t in configured}
    missing = [name for name in requested if name not in table_map]
    if missing:
        raise ValueError(f"Unknown table(s) requested: {', '.join(missing)}")

    return [table_map[name] for name in requested]


def _override_output_dir(configured: Path, override: Optional[str]) -> Path:
    if not override:
        return configured

    output_dir = Path(override).expanduser().resolve()
    if not output_dir.is_absolute():
        raise ValueError(f"Output directory must be an absolute path: {output_dir}")

    return output_dir


def _override_page_size(configured: int, override: Optional[int]) -> int:
    if override is None:
        return configured
    if override <= 0:
        raise ValueError("--page-size must be greater than zero")
    return override


def _resolve_run_output_dir(
    base_dir: Path,
    mode: str,
    *,
    now: Optional[datetime] = None,
) -> Path:
    current = now or datetime.now(timezone.utc)
    if mode == "full":
        return base_dir / "full"
    timestamp = current.strftime("%Y%m%dT%H%M%SZ")
    return base_dir / "incremental" / timestamp


def run(argv: Optional[Iterable[str]] = None) -> int:
    args = parse_args(argv)
    configure_logging(args.verbose)

    try:
        load_dotenv()

        settings = load_settings()
        settings = apply_overrides(settings, args)

        tables = list(settings.tables)
        base_output_dir = settings.output_dir
        checkpoint_store = build_checkpoint_store(
            tables,
            base_output_dir,
            args.checkpoint_path,
        )
        if args.reset_watermarks and checkpoint_store:
            logger.info("Resetting Fabric checkpoints for incremental tables")
            reset_checkpoints(checkpoint_store, tables)

        run_output_dir = _resolve_run_output_dir(base_output_dir, args.mode)
        settings = replace(settings, output_dir=run_output_dir)

        jobs = prepare_export_jobs(tables, checkpoint_store, mode=args.mode)
        logger.info("Writing CSVs to %s", settings.output_dir)
        logger.info("Requesting up to %d rows per page", settings.page_size)

        if args.dry_run:
            log_dry_run(jobs, settings.output_dir)
            return 0

        parallel_workers = args.parallel
        if parallel_workers <= 0:
            raise ValueError("--parallel must be greater than zero")

        run_exports(jobs, settings, checkpoint_store, parallel_workers)
        return 0

    except Exception as exc:  # pragma: no cover
        logger.exception("Failed to export tables: %s", exc)
        return 1


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
