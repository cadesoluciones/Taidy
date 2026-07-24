# -*- coding: utf-8 -*-
"""
CLI for uploading Factorial CSV exports to Microsoft Fabric OneLake.

Uploads both the master (full/) and every incremental run archive, mirroring
the BC pipeline layout:
  raw/factorial/full/<table>.csv
  raw/factorial/incremental/<table>/<run_ts>/<table>.csv
"""

import argparse
import logging
import os
import signal
import sys
from dataclasses import replace
from pathlib import Path, PurePosixPath
from typing import Iterable, List, Optional

from dotenv import load_dotenv

from src.config_loader import load_config_data
from src.fabric_upload.config import FabricUploadSettings
from src.fabric_upload.uploader import FabricUploader
from src.utils import configure_logging as configure_rich_logging, coerce_dir, get_logger, sanitize_segment

logger = get_logger(__name__)

CONFIG_SECTION = "factorial_upload"
DEFAULT_OUTPUT_DIR = "./exports_factorial"


def _load_settings(upload_dir: Path, *, overwrite: bool = True) -> FabricUploadSettings:
    env = dict(os.environ.items())
    secret = env.get("FABRIC_CLIENT_SECRET", "").strip()
    if not secret:
        raise ValueError("Missing required environment variable: FABRIC_CLIENT_SECRET")

    data, _ = load_config_data(None)
    section = data.get(CONFIG_SECTION)
    if not isinstance(section, dict):
        raise ValueError(f"Configuration file missing '{CONFIG_SECTION}' section")

    prefix = section.get("path_prefix", "raw").strip().strip("/")
    source = section.get("source_name", "factorial")
    checkpoint = section.get("checkpoint_path", f"raw/checkpoints/{source}").strip().strip("/")

    try:
        max_retries = int(section.get("max_retries", 3))
    except (ValueError, TypeError) as exc:
        raise ValueError("max_retries must be an integer") from exc
    if max_retries <= 0:
        raise ValueError("max_retries must be greater than zero")

    return FabricUploadSettings(
        tenant_id=section["tenant_id"].strip(),
        client_id=section["client_id"].strip(),
        client_secret=secret,
        workspace_name=section["workspace_name"].strip(),
        lakehouse_name=section["lakehouse_name"].strip(),
        workspace_id=(section.get("workspace_id") or "").strip() or None,
        lakehouse_id=(section.get("lakehouse_id") or "").strip() or None,
        remote_base=PurePosixPath(prefix) / sanitize_segment(source),
        checkpoint_root=PurePosixPath(checkpoint),
        local_export_root=Path(upload_dir).expanduser().resolve(),
        overwrite=overwrite,
        max_retries=max_retries,
    )


def _upload_dirs(output_dir: Path) -> List[Path]:
    """Returns full/ and all incremental/<run_ts>/ subdirectories that exist."""
    dirs = []
    full_dir = output_dir / "full"
    if full_dir.exists():
        dirs.append(full_dir)
    incremental_dir = output_dir / "incremental"
    if incremental_dir.exists():
        dirs.extend(sorted(p for p in incremental_dir.iterdir() if p.is_dir()))
    return dirs


def _filter_files(files: List[Path], tables: Optional[List[str]]) -> List[Path]:
    if not tables:
        return files
    return [f for f in files if f.stem in tables]


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Upload Factorial CSV exports to Fabric OneLake"
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory with Factorial CSV exports (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--tables",
        nargs="+",
        metavar="TABLE",
        help="Upload only these tables (e.g. --tables factorial_worked_times)",
    )
    parser.add_argument("--dry-run", action="store_true", help="List files without uploading")
    parser.add_argument("--skip-existing", action="store_true", help="Skip files already in OneLake")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    args, _ = parser.parse_known_args(list(argv) if argv is not None else None)
    return args


def run(argv: Optional[Iterable[str]] = None) -> int:
    args = parse_args(argv)
    level = logging.DEBUG if args.verbose else logging.INFO
    configure_rich_logging(level)
    if not args.verbose:
        for name in (
            "azure.core.pipeline.policies.http_logging_policy",
            "azure.identity",
            "azure.storage",
            "urllib3.connectionpool",
        ):
            logging.getLogger(name).setLevel(logging.WARNING)

    try:
        load_dotenv()
        output_dir = coerce_dir(args.output_dir, must_exist=True)
        overwrite = not args.skip_existing

        dirs = _upload_dirs(output_dir)
        if not dirs:
            logger.info("Nothing to upload — no full/ or incremental/ directories found.")
            return 0

        total_files = total_uploaded = total_skipped = total_failed = 0

        for upload_dir in dirs:
            settings = _load_settings(upload_dir, overwrite=overwrite)
            uploader = FabricUploader(settings)
            files = _filter_files(uploader.discover_csv_files(), args.tables)

            if args.dry_run:
                for f in files:
                    logger.info("[dry-run] Would upload: %s → %s", f.name, upload_dir.name)
                total_files += len(files)
                continue

            # A file exhausting its retries no longer aborts the batch (see
            # FabricUploader.upload_files) -- it's tallied and the remaining
            # directories are still attempted.
            uploaded, skipped, failed = uploader.upload_files(files)
            logger.info(
                "'%s': %d uploaded, %d skipped, %d failed.", upload_dir.name, uploaded, skipped, failed
            )
            total_files += len(files)
            total_uploaded += uploaded
            total_skipped += skipped
            total_failed += failed

        logger.info(
            "\n========== Factorial Upload =========="
            "\nDirectories     : %d"
            "\nFiles discovered: %d"
            "\nUploaded        : %d"
            "\nSkipped         : %d"
            "\nFailed          : %d"
            "\n======================================",
            len(dirs), total_files, total_uploaded, total_skipped, total_failed,
        )
        return 1 if total_failed else 0
    except KeyboardInterrupt:
        logger.warning("Upload interrupted by user.")
        return 130
    except Exception as exc:
        logger.exception("Factorial upload failed: %s", exc)
        return 1


def main() -> None:
    signal.signal(signal.SIGINT, lambda *_: os._exit(130))
    sys.exit(run())


if __name__ == "__main__":
    main()
