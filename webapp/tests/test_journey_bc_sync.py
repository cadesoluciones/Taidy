# -*- coding: utf-8 -*-
"""
Journey 1 (audit §4): "quiero sincronizar Business Central ahora mismo."

Fills the real BC Sync form (webapp/app.py:page_bc_sync) and confirms the
task actually launches, runs to completion, and is visible with the right
owner -- with the real subprocess swapped for a harmless stand-in (see
fake_subprocess in conftest.py), so no real BC/Fabric credentials are needed
and nothing external is touched.
"""

from __future__ import annotations

import time

from streamlit.testing.v1 import AppTest

from webapp import tasks, users_db
from webapp.tests import _page_scripts
from webapp.tests.conftest import make_user


def _wait_until_finished(task_id: str, timeout: float = 10.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        task = tasks.get_task(task_id)
        if task is not None and task.status in ("ok", "error", "stopped"):
            return
        time.sleep(0.05)


def test_operator_can_launch_bc_sync(isolated_state, fake_subprocess):
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)

    at = AppTest.from_function(_page_scripts.run_page_bc_sync)
    at.session_state["auth_user"] = {"username": "operator1", "role": users_db.ROLE_OPERATOR}
    at.run(timeout=15)
    assert not at.exception

    submit = next(b for b in at.button if b.label == "Ejecutar sync BC")
    submit.click().run(timeout=15)
    assert not at.exception
    assert any("Tarea iniciada" in s.value for s in at.success)

    all_tasks = tasks.list_tasks()
    assert len(all_tasks) == 1
    task = all_tasks[0]
    assert task.action == "sync_bc"
    assert task.triggered_by == "operator1"

    _wait_until_finished(task.id)
    assert task.status == "ok"


def test_reader_cannot_launch_bc_sync(isolated_state, fake_subprocess):
    make_user("reader1", "ReaderPass2026!", users_db.ROLE_READER)

    at = AppTest.from_function(_page_scripts.run_page_bc_sync)
    at.session_state["auth_user"] = {"username": "reader1", "role": users_db.ROLE_READER}
    at.run(timeout=15)

    submit = next(b for b in at.button if b.label == "Ejecutar sync BC")
    submit.click().run(timeout=15)
    assert not at.exception
    assert any("No tienes permiso" in e.value for e in at.error)
    assert tasks.list_tasks() == []
