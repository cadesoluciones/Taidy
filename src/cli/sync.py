"""Pipeline helper that runs extract + Fabric upload."""

from __future__ import annotations

import argparse
import sys
from typing import Iterable, Optional

from dotenv import load_dotenv

from src.fabric_upload import cli as fabric_cli
from src.main import run_extract
from src.utils import coerce_dir, get_logger

logger = get_logger(__name__)


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extract from Business Central using the usual ingest flags and then"
            " upload only the newly-created folder to Fabric."
        )
    )
    parser.add_argument(
        "--upload-dir",
        help=(
            "Optional override for the directory to upload. By default, the"
            " folder produced by the extract step is used"
            " (e.g., exports/full/ or exports/incremental/<timestamp>/)."
        ),
    )
    parser.add_argument(
        "-h2",
        action="help",
        help=argparse.SUPPRESS,
    )
    return parser.parse_known_args(list(argv) if argv is not None else None)


def run(argv: Optional[Iterable[str]] = None) -> int:
    load_dotenv()
    known_args, remaining = parse_args(argv)
    status, output_dir = run_extract(remaining)
    if status != 0:
        return status

    upload_path = (
        coerce_dir(known_args.upload_dir) if known_args.upload_dir else output_dir
    )
    fabric_args = ["--output-dir", str(upload_path)]
    result = fabric_cli.run(fabric_args)
    if result == 0:
        logger.info(
            "\n========== Sync =========="
            "\nUpload folder: %s"
            "\n===============================",
            upload_path,
        )
    return result


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
