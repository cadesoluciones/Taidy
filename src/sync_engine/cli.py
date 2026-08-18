# -*- coding: utf-8 -*-
"""
Command-line interface for the real "Sincronizar" write phase of a saved
sync mapping (see src/sync_engine/apply.py). Launched by webapp/tasks.py as
a subprocess, same pattern as extract/upload actions -- not called
in-process like the read-only comparison (src/sync_engine/compare.py),
since writes are slower, retry-heavy, and benefit from the same
stop/kill/Historial machinery every other real action already gets through
that subprocess model.
"""

import argparse
import logging
import sys
from typing import Iterable, Optional

from dotenv import load_dotenv

from .apply import DEFAULT_THRESHOLD, ApplyReport, NeedsConfirmationError, SyncApplyError, apply_mapping
from ..utils import configure_logging as configure_rich_logging, get_logger

logger = get_logger(__name__)

# Reserved exit codes so webapp/adapter.py's log parser and Task.status logic
# can tell "needs confirmation" apart from a generic failure without having
# to scrape the log text for it.
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_NEEDS_CONFIRMATION = 2


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply a saved BC<->HubSpot sync mapping for real")
    parser.add_argument("--mapping", required=True, help="Name of the sync mapping to apply")
    parser.add_argument(
        "--direction",
        required=True,
        choices=["to_target", "to_source", "both"],
        help="Which way to write: to_target, to_source, or both",
    )
    parser.add_argument(
        "--confirm-large-batch",
        action="store_true",
        help="Proceed even if pending actions exceed the quantity circuit-breaker threshold",
    )
    parser.add_argument(
        "--key",
        dest="keys",
        action="append",
        default=None,
        help="Limit to this record's matching-key value (e.g. an email); repeatable. Omit for every pending record.",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    return parser.parse_args(list(argv) if argv is not None else None)


def configure_logging(verbose: bool) -> None:
    configure_rich_logging(logging.DEBUG if verbose else logging.INFO)


def _log_records(report: ApplyReport) -> None:
    for result in report.results:
        suffix = f": {result.detail}" if result.detail else ""
        logger.info("[%s] key=%r -> %s%s", result.kind, result.key, result.outcome, suffix)


def _log_summary(report: ApplyReport) -> None:
    logger.info(
        "\n========== Sincronización: %s (%s) =========="
        "\nCreados  : %d"
        "\nActualiz.: %d"
        "\nOmitidos : %d"
        "\nFallidos : %d"
        "\n===============================================",
        report.mapping_name,
        report.direction,
        report.created,
        report.updated,
        report.skipped,
        report.failed,
    )


def run(argv: Optional[Iterable[str]] = None) -> int:
    args = parse_args(argv)
    configure_logging(args.verbose)

    try:
        load_dotenv()
        report = apply_mapping(
            args.mapping,
            direction=args.direction,
            confirmed=args.confirm_large_batch,
            only_keys=set(args.keys) if args.keys else None,
        )
    except NeedsConfirmationError as exc:
        logger.error("NEEDS_CONFIRMATION pending=%d threshold=%d", exc.pending_count, DEFAULT_THRESHOLD)
        return EXIT_NEEDS_CONFIRMATION
    except SyncApplyError as exc:
        logger.error("Sincronización fallida: %s", exc)
        return EXIT_FAILED
    except Exception as exc:  # pragma: no cover
        logger.exception("Sincronización fallida: %s", exc)
        return EXIT_FAILED

    _log_records(report)
    _log_summary(report)
    return EXIT_FAILED if report.failed else EXIT_OK


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":  # pragma: no cover
    main()
