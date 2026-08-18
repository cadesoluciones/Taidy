# -*- coding: utf-8 -*-
"""
webapp/adapter.py -- build_sync_apply_argv/parse_sync_apply_records, the
argv builder and log parser for the sync_apply task (see
src/sync_engine/cli.py for the log line format these parse).
"""

from __future__ import annotations

from webapp.adapter import build_sync_apply_argv, parse_sync_apply_records


def test_build_sync_apply_argv_minimal():
    argv = build_sync_apply_argv(mapping="m1", direction="both")
    assert argv == ["--mapping", "m1", "--direction", "both"]


def test_build_sync_apply_argv_with_flags():
    argv = build_sync_apply_argv(mapping="m1", direction="to_target", confirm_large_batch=True, verbose=True)
    assert argv == ["--mapping", "m1", "--direction", "to_target", "--confirm-large-batch", "--verbose"]


def test_build_sync_apply_argv_with_keys():
    argv = build_sync_apply_argv(mapping="m1", direction="both", keys=["a@x.com", "b@x.com"])
    assert argv == ["--mapping", "m1", "--direction", "both", "--key", "a@x.com", "--key", "b@x.com"]


def test_build_sync_apply_argv_without_keys_omits_the_flag():
    argv = build_sync_apply_argv(mapping="m1", direction="both", keys=None)
    assert "--key" not in argv


def test_parse_sync_apply_records_reads_kind_key_outcome_and_detail():
    log = (
        "some unrelated line\n"
        "[create_target] key='a@x.com' -> created\n"
        "[update_source] key='b@x.com' -> failed: conflicto persistente\n"
        "[update_target] key='c@x.com' -> skipped: ya sincronizado\n"
    )

    records = {r.key: r for r in parse_sync_apply_records(log)}

    assert records["a@x.com"].kind == "create_target"
    assert records["a@x.com"].outcome == "created"
    assert records["a@x.com"].detail == ""

    assert records["b@x.com"].outcome == "failed"
    assert records["b@x.com"].detail == "conflicto persistente"

    assert records["c@x.com"].outcome == "skipped"


def test_parse_sync_apply_records_last_occurrence_wins_for_the_same_kind_and_key():
    log = "[update_target] key='a@x.com' -> failed: primero\n" "[update_target] key='a@x.com' -> updated\n"

    records = parse_sync_apply_records(log)

    assert len(records) == 1
    assert records[0].outcome == "updated"


def test_parse_sync_apply_records_ignores_unrelated_log_lines():
    log = "\n========== Sincronización: m1 (both) ==========\nCreados  : 1\n"
    assert parse_sync_apply_records(log) == []
