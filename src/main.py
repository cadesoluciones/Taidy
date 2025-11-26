"""Entry point for the Business Central data extraction PoC.

Run this module as a script to download configured tables into CSV files. The
script expects configuration via environment variables (see `.env.example`) and
supports basic CLI overrides for ad-hoc experimentation.
"""

import argparse
import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Iterable, List, Optional

from dotenv import load_dotenv

from bc_client.auth import OAuthTokenProvider
from bc_client.config import DEFAULT_PAGE_SIZE, Settings, TableConfig, load_settings
from bc_client.api import BusinessCentralClient
from bc_client.exporter import export_table


# ---------------------------
# CLI / config
# ---------------------------


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Business Central tables to CSV"
    )
    parser.add_argument("--tables", nargs="*", help="Override configured table list")
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
    return parser.parse_args(list(argv) if argv is not None else None)


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")


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


# ---------------------------
# Client creation
# ---------------------------


def create_token_provider(settings: Settings) -> OAuthTokenProvider:
    return OAuthTokenProvider(
        token_url=settings.token_url,
        client_id=settings.client_id,
        client_secret=settings.client_secret,
        scope=settings.scope,
        session=None,
        timeout=30,
    )


def create_client(
    settings: Settings,
    token_provider: OAuthTokenProvider,
) -> BusinessCentralClient:
    return BusinessCentralClient(
        settings=settings,
        token_provider=token_provider,
        session=None,
        timeout=30,
    )


# ---------------------------
# Export logic
# ---------------------------


def export_single_table(
    table: TableConfig,
    client: BusinessCentralClient,
    output_dir: Path,
) -> Path:
    logging.info("Exporting table '%s'", table.name)

    rows = client.get_table_rows(table.url, label=table.name)
    destination = export_table(table.name, rows, output_dir)

    logging.info("Saved %s", destination)
    return destination


def export_tables(
    tables: List[TableConfig],
    settings: Settings,
    token_provider: OAuthTokenProvider,
    parallel_workers: int,
) -> None:
    if parallel_workers <= 1:
        client = create_client(settings, token_provider)
        for table in tables:
            export_single_table(table, client, settings.output_dir)
        return

    logging.info("Running exports with up to %d parallel workers", parallel_workers)

    # Each worker uses its own client (safer for requests sessions).
    def worker(table: TableConfig) -> Path:
        client = create_client(settings, token_provider)
        return export_single_table(table, client, settings.output_dir)

    errors: List[Exception] = []
    with ThreadPoolExecutor(max_workers=parallel_workers) as executor:
        for table, result in zip(tables, executor.map(worker, tables)):
            try:
                _ = result  # ensures exceptions surface here
            except Exception as exc:
                logging.exception("Export failed for table '%s'", table.name)
                errors.append(exc)

    if errors:
        raise RuntimeError("One or more table exports failed") from errors[0]


# ---------------------------
# Main run
# ---------------------------


def run(argv: Optional[Iterable[str]] = None) -> int:
    args = parse_args(argv)
    configure_logging(args.verbose)

    try:
        load_dotenv()

        settings = load_settings()
        settings = apply_overrides(settings, args)

        tables = list(settings.tables)
        logging.info("Requesting up to %d rows per page", settings.page_size)

        if args.dry_run:
            log_dry_run(tables, settings.output_dir)
            return 0

        parallel_workers = args.parallel
        if parallel_workers <= 0:
            raise ValueError("--parallel must be greater than zero")

        token_provider = create_token_provider(settings)

        export_tables(tables, settings, token_provider, parallel_workers)
        return 0

    except Exception as exc:  # pragma: no cover
        logging.exception("Failed to export tables: %s", exc)
        return 1


def log_dry_run(tables: List[TableConfig], output_dir: Path) -> None:
    for table in tables:
        logging.info(
            "[dry-run] would export table '%s' from %s to %s",
            table.name,
            table.url,
            output_dir,
        )


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
