"""Standalone CLI entry point for uploading exports to Fabric OneLake."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Iterable, Optional

from dotenv import load_dotenv

from .config import load_fabric_settings
from .uploader import FabricUploader


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Upload existing CSV exports to Fabric OneLake",
    )
    parser.add_argument(
        "--output-dir",
        default="./exports",
        help="Directory containing CSV exports (default: ./exports)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List files without uploading",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")


def _resolve_output_dir(raw: str) -> Path:
    output_dir = Path(raw).expanduser().resolve()
    if not output_dir.exists():
        raise FileNotFoundError(
            f"Output directory '{output_dir}' does not exist; run the ingest task first"
        )
    return output_dir


def run(argv: Optional[Iterable[str]] = None) -> int:
    args = parse_args(argv)
    configure_logging(args.verbose)

    try:
        load_dotenv()
        output_dir = _resolve_output_dir(args.output_dir)
        settings = load_fabric_settings(output_dir, force_enable=True)
        uploader = FabricUploader(settings)
        files = uploader.discover_csv_files()
        if args.dry_run:
            for csv_file in files:
                logging.info("[dry-run] would upload %s", csv_file)
            if not files:
                logging.info(
                    "[dry-run] no CSV files found under '%s'",
                    settings.local_export_root,
                )
            return 0
        uploader.upload_files(files)
        return 0
    except Exception as exc:  # pragma: no cover - defensive
        logging.exception("Fabric upload failed: %s", exc)
        return 1


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":  # pragma: no cover
    main()
