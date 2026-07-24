# -*- coding: utf-8 -*-
"""
Regression test for a real bug found while investigating a user report:
"a veces una tarea que sigue en ejecución se muestra como error".

Root cause: parse_bc_extract_tables()/parse_factorial_extract_tables() treated
"table started but no completion line yet" as _STATUS_ERROR unconditionally --
which is completely normal while the task is still running (especially with
--parallel > 1, where several tables are simultaneously "started but not
finished"). The task's own status badge stayed correct ("En curso"); only the
per-table breakdown lied. Fixed by threading the task's actual terminal/
non-terminal state through as `finished`, so the ambiguous case only resolves
to "error" once the process has genuinely exited without confirming that
table -- exactly matching the pattern parse_upload_files() already used.
"""

from __future__ import annotations

from datetime import datetime, timezone

from webapp import adapter, tasks


def _make_task(status: str) -> tasks.Task:
    task = tasks.Task(
        id="t1",
        action="extract_bc",
        triggered_by="admin",
        started_at=datetime.now(timezone.utc).isoformat(),
        expected_tables=["customers", "invoices"],
    )
    task.status = status
    task._append_log("Exporting table 'customers'\n")
    task._append_log("Exporting table 'invoices'\n")
    task._append_log("Table 'customers' export complete; 120 rows written to 'x.csv'\n")
    return task


def test_mid_export_table_is_in_progress_while_task_is_running():
    task = _make_task("running")
    statuses = {s.name: s.status for s in task.table_statuses()}
    assert statuses["customers"] == "ok"
    assert statuses["invoices"] == "in_progress"


def test_mid_export_table_is_still_flagged_as_error_once_task_finished():
    task = _make_task("error")
    statuses = {s.name: s.status for s in task.table_statuses()}
    assert statuses["customers"] == "ok"
    assert statuses["invoices"] == "error"


def test_adapter_parser_directly_for_both_bc_and_factorial():
    log = "Exporting table 'x'\n"
    assert adapter.parse_bc_extract_tables(["x"], log, finished=False)[0].status == "in_progress"
    assert adapter.parse_bc_extract_tables(["x"], log, finished=True)[0].status == "error"

    log_fac = "Fetching 'x'\n"
    assert adapter.parse_factorial_extract_tables(["x"], log_fac, finished=False)[0].status == "in_progress"
    assert adapter.parse_factorial_extract_tables(["x"], log_fac, finished=True)[0].status == "error"
