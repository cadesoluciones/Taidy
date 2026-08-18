# -*- coding: utf-8 -*-
"""
src/sync_engine/cli.py -- exit-code mapping (0 ok / 1 failed or error / 2
needs confirmation) is what webapp/tasks.py relies on to tell these apart
without scraping the log text, so it's the main thing pinned down here.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.sync_engine import cli as cli_module  # noqa: E402
from src.sync_engine.apply import ApplyReport, NeedsConfirmationError, RecordResult, SyncApplyError  # noqa: E402


def test_parse_args_requires_mapping_and_direction():
    with pytest.raises(SystemExit):
        cli_module.parse_args([])


def test_parse_args_reads_all_flags():
    args = cli_module.parse_args(["--mapping", "m1", "--direction", "both", "--confirm-large-batch", "--verbose"])
    assert args.mapping == "m1"
    assert args.direction == "both"
    assert args.confirm_large_batch is True
    assert args.verbose is True


def test_parse_args_rejects_an_invalid_direction():
    with pytest.raises(SystemExit):
        cli_module.parse_args(["--mapping", "m1", "--direction", "sideways"])


def test_parse_args_collects_repeated_key_flags():
    args = cli_module.parse_args(
        ["--mapping", "m1", "--direction", "both", "--key", "a@x.com", "--key", "b@x.com"]
    )
    assert args.keys == ["a@x.com", "b@x.com"]


def test_parse_args_keys_defaults_to_none():
    args = cli_module.parse_args(["--mapping", "m1", "--direction", "both"])
    assert args.keys is None


def test_run_passes_only_keys_as_a_set(monkeypatch):
    captured = {}

    def fake_apply_mapping(mapping, *, direction, confirmed, only_keys):
        captured["only_keys"] = only_keys
        return ApplyReport(mapping_name=mapping, direction=direction, results=[])

    monkeypatch.setattr(cli_module, "apply_mapping", fake_apply_mapping)

    cli_module.run(["--mapping", "m1", "--direction", "both", "--key", "a@x.com", "--key", "b@x.com"])
    assert captured["only_keys"] == {"a@x.com", "b@x.com"}


def test_run_passes_none_when_no_keys_given(monkeypatch):
    captured = {}

    def fake_apply_mapping(mapping, *, direction, confirmed, only_keys):
        captured["only_keys"] = only_keys
        return ApplyReport(mapping_name=mapping, direction=direction, results=[])

    monkeypatch.setattr(cli_module, "apply_mapping", fake_apply_mapping)

    cli_module.run(["--mapping", "m1", "--direction", "both"])
    assert captured["only_keys"] is None


def test_run_maps_needs_confirmation_to_exit_code_2(monkeypatch, caplog):
    def fake_apply_mapping(mapping, *, direction, confirmed, only_keys=None):
        raise NeedsConfirmationError(pending_count=75)

    monkeypatch.setattr(cli_module, "apply_mapping", fake_apply_mapping)
    # configure_logging() clears the root logger's handlers (it installs a
    # Rich handler for real runs) -- that would also wipe caplog's handler,
    # so it's stubbed out here; it's not what this test is about.
    monkeypatch.setattr(cli_module, "configure_logging", lambda verbose: None)

    with caplog.at_level("ERROR"):
        code = cli_module.run(["--mapping", "m1", "--direction", "both"])

    assert code == cli_module.EXIT_NEEDS_CONFIRMATION
    assert any("NEEDS_CONFIRMATION" in r.message and "pending=75" in r.message for r in caplog.records)


def test_run_maps_sync_apply_error_to_exit_code_1(monkeypatch):
    def fake_apply_mapping(mapping, *, direction, confirmed, only_keys=None):
        raise SyncApplyError("no existe el mapeo")

    monkeypatch.setattr(cli_module, "apply_mapping", fake_apply_mapping)

    code = cli_module.run(["--mapping", "m1", "--direction", "both"])
    assert code == cli_module.EXIT_FAILED


def test_run_returns_0_when_nothing_failed(monkeypatch):
    report = ApplyReport(
        mapping_name="m1",
        direction="both",
        results=[RecordResult(key="a@x.com", kind="create_target", outcome="created")],
    )
    monkeypatch.setattr(cli_module, "apply_mapping", lambda mapping, *, direction, confirmed, only_keys=None: report)

    code = cli_module.run(["--mapping", "m1", "--direction", "both"])
    assert code == cli_module.EXIT_OK


def test_run_returns_1_when_something_failed(monkeypatch):
    report = ApplyReport(
        mapping_name="m1",
        direction="both",
        results=[RecordResult(key="a@x.com", kind="create_target", outcome="failed", detail="boom")],
    )
    monkeypatch.setattr(cli_module, "apply_mapping", lambda mapping, *, direction, confirmed, only_keys=None: report)

    code = cli_module.run(["--mapping", "m1", "--direction", "both"])
    assert code == cli_module.EXIT_FAILED


def test_run_logs_one_line_per_record_with_detail(monkeypatch, caplog):
    report = ApplyReport(
        mapping_name="m1",
        direction="both",
        results=[
            RecordResult(key="a@x.com", kind="create_target", outcome="created"),
            RecordResult(key="b@x.com", kind="update_source", outcome="failed", detail="conflicto"),
        ],
    )
    monkeypatch.setattr(cli_module, "apply_mapping", lambda mapping, *, direction, confirmed, only_keys=None: report)
    monkeypatch.setattr(cli_module, "configure_logging", lambda verbose: None)

    with caplog.at_level("INFO"):
        cli_module.run(["--mapping", "m1", "--direction", "both"])

    messages = [r.message for r in caplog.records]
    assert any("create_target" in m and "a@x.com" in m and "created" in m for m in messages)
    assert any("update_source" in m and "b@x.com" in m and "conflicto" in m for m in messages)


def test_run_passes_confirm_large_batch_flag_through(monkeypatch):
    captured = {}

    def fake_apply_mapping(mapping, *, direction, confirmed, only_keys=None):
        captured["confirmed"] = confirmed
        return ApplyReport(mapping_name=mapping, direction=direction, results=[])

    monkeypatch.setattr(cli_module, "apply_mapping", fake_apply_mapping)

    cli_module.run(["--mapping", "m1", "--direction", "to_target", "--confirm-large-batch"])
    assert captured["confirmed"] is True
