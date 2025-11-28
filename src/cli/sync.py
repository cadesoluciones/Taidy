"""Pipeline helper that runs extract + Fabric upload."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable, Optional

from dotenv import load_dotenv

from src.fabric_upload import cli as fabric_cli
from src.main import run_extract


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run extract + Fabric upload")
    parser.add_argument(
        "--upload-dir",
        help=(
            "Optional override for the directory to upload. By default, the"
            " folder produced by the extract step is used."
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
        Path(known_args.upload_dir).expanduser().resolve()
        if known_args.upload_dir
        else output_dir
    )
    if not upload_path:
        raise RuntimeError("Upload path could not be determined")
    fabric_args = ["--output-dir", str(upload_path)]
    return fabric_cli.run(fabric_args)


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
