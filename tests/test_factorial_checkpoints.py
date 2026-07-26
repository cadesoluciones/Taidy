# -*- coding: utf-8 -*-
"""
src/factorial_client/checkpoints.py drives which date range a recurring
Factorial incremental extract actually requests (resolve_start_on): get the
overlap-days math wrong and every scheduled run either re-fetches weeks of
already-extracted data or silently skips a gap. Had zero test coverage.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.factorial_client import checkpoints  # noqa: E402


def test_save_then_load_roundtrips_the_date(tmp_path: Path):
    checkpoints.save("employees", date(2026, 3, 15), tmp_path)

    assert checkpoints.load("employees", tmp_path) == date(2026, 3, 15)


def test_load_with_no_checkpoint_returns_none(tmp_path: Path):
    assert checkpoints.load("employees", tmp_path) is None


def test_load_with_corrupted_checkpoint_returns_none_instead_of_raising(tmp_path: Path):
    path = checkpoints.checkpoint_dir(tmp_path) / "employees.json"
    path.parent.mkdir(parents=True)
    path.write_text("not valid json", encoding="utf-8")

    assert checkpoints.load("employees", tmp_path) is None


def test_reset_deletes_only_the_named_table(tmp_path: Path):
    checkpoints.save("employees", date(2026, 1, 1), tmp_path)
    checkpoints.save("contracts", date(2026, 1, 1), tmp_path)

    checkpoints.reset("employees", tmp_path)

    assert checkpoints.load("employees", tmp_path) is None
    assert checkpoints.load("contracts", tmp_path) == date(2026, 1, 1)


def test_reset_on_a_table_with_no_checkpoint_does_not_raise(tmp_path: Path):
    checkpoints.reset("never_saved", tmp_path)  # must not raise


def test_reset_all_clears_every_table(tmp_path: Path):
    checkpoints.save("employees", date(2026, 1, 1), tmp_path)
    checkpoints.save("contracts", date(2026, 1, 1), tmp_path)

    checkpoints.reset_all(tmp_path)

    assert checkpoints.load("employees", tmp_path) is None
    assert checkpoints.load("contracts", tmp_path) is None


def test_reset_all_with_no_checkpoint_dir_does_not_raise(tmp_path: Path):
    checkpoints.reset_all(tmp_path / "never_created")  # must not raise


def test_resolve_start_on_falls_back_when_no_checkpoint(tmp_path: Path):
    fallback = date(2025, 1, 1)

    effective = checkpoints.resolve_start_on("employees", fallback, tmp_path, overlap_days=3)

    assert effective == fallback


def test_resolve_start_on_subtracts_overlap_from_the_checkpoint(tmp_path: Path):
    checkpoints.save("employees", date(2026, 3, 15), tmp_path)

    effective = checkpoints.resolve_start_on(
        "employees", date(2025, 1, 1), tmp_path, overlap_days=3
    )

    assert effective == date(2026, 3, 15) - timedelta(days=3)


def test_resolve_start_on_zero_overlap_returns_checkpoint_unchanged(tmp_path: Path):
    checkpoints.save("employees", date(2026, 3, 15), tmp_path)

    effective = checkpoints.resolve_start_on(
        "employees", date(2025, 1, 1), tmp_path, overlap_days=0
    )

    assert effective == date(2026, 3, 15)
