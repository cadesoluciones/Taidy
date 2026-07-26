# -*- coding: utf-8 -*-
"""
Proactive alerts: simple business-rule detections over data the app already
has (run_history.json), surfaced on the dashboard so a repeatedly-failing
action doesn't go unnoticed until someone happens to open Historial and
scroll -- e.g. a BC/Factorial credential expiring shows up as several
consecutive sync failures well before anyone would otherwise notice.
"""

from __future__ import annotations

from typing import Dict, List, Optional, TypedDict

from webapp import history

# How many of an action's most recent runs to look at, and how many of those
# have to be failures to raise an alert. 3-of-5 (or worse) means the last
# couple of attempts weren't a fluke -- something about that action is
# consistently broken right now.
_RECENT_SAMPLE_SIZE = 5
_MIN_SAMPLES = 3
_FAILURE_RATE_THRESHOLD = 0.6


class ErrorRateAlert(TypedDict):
    action: str
    recent_failures: int
    recent_total: int


def detect_elevated_error_rates(entries: Optional[List[dict]] = None) -> List[ErrorRateAlert]:
    """entries: newest-first history entries (defaults to the full retained
    history). A manually-"stopped" run is excluded -- a deliberate stop
    isn't evidence the action itself is failing.
    """
    if entries is None:
        entries = history.get_history(limit=200)

    by_action: Dict[str, List[dict]] = {}
    for e in entries:
        if e.get("status") == "stopped":
            continue
        by_action.setdefault(e["action"], []).append(e)

    alerts: List[ErrorRateAlert] = []
    for action, runs in by_action.items():
        recent = runs[:_RECENT_SAMPLE_SIZE]
        if len(recent) < _MIN_SAMPLES:
            continue
        failures = sum(1 for r in recent if not r["ok"])
        if failures / len(recent) >= _FAILURE_RATE_THRESHOLD:
            alerts.append({"action": action, "recent_failures": failures, "recent_total": len(recent)})

    return sorted(alerts, key=lambda a: a["recent_failures"], reverse=True)
