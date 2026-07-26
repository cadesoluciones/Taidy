# -*- coding: utf-8 -*-
"""
detect_elevated_error_rates() flags an action whose most recent runs are
mostly failures -- e.g. an expired BC credential shows up as several
consecutive sync_bc failures. Tests build history entries directly (newest
first, matching webapp/history.get_history()'s contract) rather than going
through record_run()/isolated_state, since the function only cares about the
shape of what it's handed.
"""

from __future__ import annotations

from typing import Optional

from webapp import alerts


def _entry(action: str, ok: bool, status: Optional[str] = None) -> dict:
    return {"action": action, "ok": ok, "status": status or ("ok" if ok else "error")}


def test_flags_an_action_with_a_majority_of_recent_failures():
    entries = [
        _entry("sync_bc", ok=False),
        _entry("sync_bc", ok=False),
        _entry("sync_bc", ok=False),
        _entry("sync_bc", ok=True),
        _entry("sync_bc", ok=True),
    ]

    result = alerts.detect_elevated_error_rates(entries)

    assert result == [{"action": "sync_bc", "recent_failures": 3, "recent_total": 5}]


def test_does_not_flag_a_mostly_successful_action():
    entries = [_entry("sync_bc", ok=True)] * 4 + [_entry("sync_bc", ok=False)]

    assert alerts.detect_elevated_error_rates(entries) == []


def test_does_not_flag_with_too_few_samples():
    entries = [_entry("sync_bc", ok=False), _entry("sync_bc", ok=False)]  # only 2, below _MIN_SAMPLES

    assert alerts.detect_elevated_error_rates(entries) == []


def test_only_looks_at_the_most_recent_sample_window():
    """5 older failures followed by 5 recent successes must NOT be flagged --
    whatever was wrong is fixed now."""
    entries = [_entry("sync_bc", ok=True)] * 5 + [_entry("sync_bc", ok=False)] * 5

    assert alerts.detect_elevated_error_rates(entries) == []


def test_a_manual_stop_does_not_count_as_a_failure_or_a_sample():
    entries = [
        _entry("sync_bc", ok=False, status="stopped"),
        _entry("sync_bc", ok=False, status="stopped"),
        _entry("sync_bc", ok=False),
        _entry("sync_bc", ok=False),
        _entry("sync_bc", ok=False),
    ]

    result = alerts.detect_elevated_error_rates(entries)

    assert result == [{"action": "sync_bc", "recent_failures": 3, "recent_total": 3}]


def test_multiple_actions_are_tracked_independently():
    entries = (
        [_entry("sync_bc", ok=False)] * 3
        + [_entry("sync_bc", ok=True)] * 2
        + [_entry("extract_factorial", ok=True)] * 5
    )

    result = alerts.detect_elevated_error_rates(entries)

    assert [a["action"] for a in result] == ["sync_bc"]


def test_results_are_sorted_by_most_failures_first():
    entries = (
        [_entry("upload_bc", ok=False)] * 3
        + [_entry("upload_bc", ok=True)] * 2
        + [_entry("sync_factorial", ok=False)] * 5
    )

    result = alerts.detect_elevated_error_rates(entries)

    assert [a["action"] for a in result] == ["sync_factorial", "upload_bc"]


def test_defaults_to_reading_from_history_when_no_entries_given(isolated_state):
    from webapp import history

    for _ in range(4):
        history.record_run(action="sync_bc", source="admin", status="error", ok=False, message="boom", log="")

    result = alerts.detect_elevated_error_rates()

    assert result == [{"action": "sync_bc", "recent_failures": 4, "recent_total": 4}]
