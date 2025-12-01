# -*- coding: utf-8 -*-
"""
Standalone command-line interface for uploading existing CSV exports to
Microsoft Fabric OneLake.

This script allows users to trigger the upload process independently of the main
data extraction. It is useful for re-uploading files, validating exports before
uploading, or running uploads on a separate schedule.
"""

# --------------------------------------------------------------------------------------
# Imports
# --------------------------------------------------------------------------------------

import argparse
import logging
import sys
from pathlib import Path
from typing import Iterable, Optional

from dotenv import load_dotenv

from .config import load_fabric_settings
from .uploader import FabricUploader
from ..utils import configure_logging as configure_rich_logging, get_logger

# --------------------------------------------------------------------------------------
# Constants and Global Variables
# --------------------------------------------------------------------------------------

logger = get_logger(__name__)


# --------------------------------------------------------------------------------------
# CLI Argument Parsing
# --------------------------------------------------------------------------------------


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    """
    Defines and parses command-line arguments for the Fabric upload script.

    Args:
        argv: Optional command-line arguments for testing.

    Returns:
        An `argparse.Namespace` object with the parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description="Upload existing CSV exports to Fabric OneLake",
    )
    parser.add_argument(
        "--output-dir",
        default="./exports",
        help="Directory containing the CSV export folders (e.g., 'full' or 'incremental/timestamp')",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging for detailed output.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List files that would be uploaded without actually uploading them.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip uploading files that already exist in OneLake (default is to overwrite).",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


# --------------------------------------------------------------------------------------
# Logging and Summarization
# --------------------------------------------------------------------------------------


def configure_logging(verbose: bool) -> None:
    """
    Sets up application-wide logging for the upload CLI.

    Args:
        verbose: If True, sets logging to DEBUG; otherwise, INFO.
    """
    level = logging.DEBUG if verbose else logging.INFO
    configure_rich_logging(level)

    # Suppress noisy logging from the Azure SDK unless in verbose mode.
    if not verbose:
        azure_loggers = [
            "azure.core.pipeline.policies.http_logging_policy",
            "azure.identity",
            "azure.storage",
            "urllib3.connectionpool",
        ]
        for logger_name in azure_loggers:
            logging.getLogger(logger_name).setLevel(logging.WARNING)


def _log_summary(
    *,
    header: str,
    files: int,
    uploaded: int,
    skipped: int,
    source: Path,
) -> None:
    """
    Logs a formatted summary of the upload run.
    """
    logger.info(
        "\n========== %s =========="
        "\nFiles discovered: %d"
        "\nUploaded        : %d"
        "\nSkipped         : %d"
        "\nLocal source    : %s"
        "\n===============================",
        header,
        files,
        uploaded,
        skipped,
        source,
    )


# --------------------------------------------------------------------------------------
# Core Logic
# --------------------------------------------------------------------------------------


def _resolve_output_dir(raw: str) -> Path:
    """
    Resolves the provided output directory path and ensures it exists.

    Args:
        raw: The raw string path from the command line.

    Returns:
        An absolute, resolved `Path` object.
    """
    output_dir = Path(raw).expanduser().resolve()
    if not output_dir.exists():
        raise FileNotFoundError(
            f"Output directory '{output_dir}' does not exist; run the ingest task first."
        )
    return output_dir


def run(argv: Optional[Iterable[str]] = None) -> int:
    """
    Main orchestration function for the Fabric upload process.

    Handles argument parsing, configuration loading, file discovery, and execution
    of the upload (or dry run).

    Args:
        argv: Optional command-line arguments for testing.

    Returns:
        An exit code: 0 for success, 1 for failure.
    """
    args = parse_args(argv)
    configure_logging(args.verbose)

    try:
        # Load secrets from .env file.
        load_dotenv()

        # Resolve path and load settings; force_enable=True makes this CLI
        # always attempt an upload, ignoring the 'enabled' flag in config.
        output_dir = _resolve_output_dir(args.output_dir)
        settings = load_fabric_settings(output_dir, force_enable=True)

        # The --skip-existing flag overrides the `overwrite` setting from config.
        if settings and args.skip_existing:
            from dataclasses import replace

            settings = replace(settings, overwrite=False)

        # Initialize the uploader and discover files.
        uploader = FabricUploader(settings)
        files = uploader.discover_csv_files()

        # Handle dry-run mode.
        if args.dry_run:
            for csv_file in files:
                logger.info("[dry-run] Would upload: %s", csv_file.name)
            _log_summary(
                header="Fabric Upload (dry-run)",
                files=len(files),
                uploaded=0,  # Nothing is actually uploaded
                skipped=len(files),
                source=settings.local_export_root,
            )
            return 0

        # Execute the actual upload.
        uploaded, skipped = uploader.upload_files(files)
        _log_summary(
            header="Fabric Upload",
            files=len(files),
            uploaded=uploaded,
            skipped=skipped,
            source=settings.local_export_root,
        )
        return 0
    except Exception as exc:  # pragma: no cover
        logger.exception("Fabric upload failed: %s", exc)
        return 1


# --------------------------------------------------------------------------------------
# Script Execution
# --------------------------------------------------------------------------------------


def main() -> None:
    """
    Entry point for running the script directly.
    """
    sys.exit(run())


if __name__ == "__main__":  # pragma: no cover
    main()
