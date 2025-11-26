"""Entry point for the Business Central data extraction PoC.

Run this module as a script to download configured tables into CSV files. The
script expects configuration via environment variables (see `.env.example`) and
supports basic CLI overrides for ad-hoc experimentation.
"""

import argparse
import logging
import sys
from dataclasses import replace
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv

from bc_client.auth import OAuthTokenProvider
from bc_client.config import DEFAULT_PAGE_SIZE, Settings, load_settings
from bc_client.api import BusinessCentralClient
from bc_client.exporter import export_table


def _parse_args(argv: Iterable[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Business Central tables to CSV"
    )
    parser.add_argument("--tables", nargs="*", help="Override configured table list")
    parser.add_argument("--output-dir", help="Override CSV output directory")
    parser.add_argument(
        "--page-size",
        type=int,
        help=f"Override Business Central page size (defaults to BC_PAGE_SIZE or {DEFAULT_PAGE_SIZE})",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Log actions without calling the API"
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    return parser.parse_args(list(argv) if argv is not None else None)


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")


def _apply_overrides(settings: Settings, args: argparse.Namespace) -> Settings:
    tables = settings.tables
    if args.tables:
        requested = [name for name in args.tables if name]
        if not requested:
            raise ValueError(
                "At least one table name must be provided when using --tables"
            )

        table_map = {table.name: table for table in settings.tables}
        missing = [name for name in requested if name not in table_map]
        if missing:
            raise ValueError(f"Unknown table(s) requested: {', '.join(missing)}")
        tables = [table_map[name] for name in requested]

    output_dir = settings.output_dir
    if args.output_dir:
        output_dir = Path(args.output_dir).expanduser()

    page_size = settings.page_size
    if args.page_size is not None:
        if args.page_size <= 0:
            raise ValueError("--page-size must be greater than zero")
        page_size = args.page_size

    return replace(
        settings, tables=list(tables), output_dir=output_dir, page_size=page_size
    )


def _create_token_provider(settings: Settings) -> OAuthTokenProvider:
    return OAuthTokenProvider(
        token_url=settings.token_url,
        client_id=settings.client_id,
        client_secret=settings.client_secret,
        scope=settings.scope,
        session=None,
        timeout=30,
    )


def _create_client(
    settings: Settings, token_provider: OAuthTokenProvider
) -> BusinessCentralClient:
    return BusinessCentralClient(
        settings=settings,
        token_provider=token_provider,
        session=None,
        timeout=30,
    )


def run(argv: Iterable[str] | None = None) -> int:
    args = _parse_args(argv)
    _configure_logging(args.verbose)

    try:
        load_dotenv()
        settings = load_settings()
        settings = _apply_overrides(settings, args)
        tables = settings.tables
        logging.info("Requesting up to %s rows per page", settings.page_size)

        if args.dry_run:
            for table in tables:
                logging.info(
                    "[dry-run] would export table '%s' from %s to %s",
                    table.name,
                    table.url,
                    settings.output_dir,
                )
            return 0

        token_provider = _create_token_provider(settings)
        client = _create_client(settings, token_provider)

        for table in tables:
            logging.info("Exporting table '%s'", table.name)
            destination = export_table(
                table.name,
                client.iter_table_rows(table.url, label=table.name),
                settings.output_dir,
            )
            logging.info("Saved %s", destination)

        return 0
    except Exception as exc:  # pragma: no cover - defensive logging
        logging.exception("Failed to export tables: %s", exc)
        return 1


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
