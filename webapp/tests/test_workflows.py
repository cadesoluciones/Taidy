# -*- coding: utf-8 -*-
"""
Reader-access unit tests for webapp/workflows.py -- the API-layer tests in
api/tests/test_workflows.py cover the same behavior end-to-end through
FastAPI; these exercise the business-logic functions directly.
"""

from __future__ import annotations

import pytest

from webapp import workflows
from webapp.users_db import ROLE_ADMIN, ROLE_OPERATOR, ROLE_READER

_STEPS = [{"id": "a", "label": "Paso A", "action": "extract_bc", "params": {}, "depends_on": [], "trigger_rule": "all_success"}]


def test_create_workflow_starts_with_no_reader_access(isolated_state):
    workflow = workflows.create_workflow("Flujo 1", _STEPS)
    assert workflow["reader_allowed_users"] == []


def test_set_reader_access_deduplicates_and_drops_blanks(isolated_state):
    workflow = workflows.create_workflow("Flujo 1", _STEPS)
    updated = workflows.set_reader_access(workflow["id"], ["rrhh1", "rrhh1", "  ", "compras1"])
    assert updated["reader_allowed_users"] == ["compras1", "rrhh1"]


def test_set_reader_access_on_unknown_workflow_raises(isolated_state):
    with pytest.raises(ValueError, match="desconocido"):
        workflows.set_reader_access("does-not-exist", ["reader1"])


def test_update_workflow_preserves_reader_access(isolated_state):
    workflow = workflows.create_workflow("Flujo 1", _STEPS)
    workflows.set_reader_access(workflow["id"], ["rrhh1"])
    updated = workflows.update_workflow(workflow["id"], "Flujo renombrado", _STEPS)
    assert updated["reader_allowed_users"] == ["rrhh1"]


def test_list_workflows_for_user_operator_and_admin_see_everything(isolated_state):
    workflows.create_workflow("Flujo 1", _STEPS)
    workflows.create_workflow("Flujo 2", _STEPS)

    assert len(workflows.list_workflows_for_user("someop", ROLE_OPERATOR)) == 2
    assert len(workflows.list_workflows_for_user("someadmin", ROLE_ADMIN)) == 2


def test_list_workflows_for_user_reader_sees_only_assigned(isolated_state):
    rrhh = workflows.create_workflow("Flujo RRHH", _STEPS)
    workflows.create_workflow("Flujo Compras", _STEPS)
    workflows.set_reader_access(rrhh["id"], ["rrhh1"])

    visible = workflows.list_workflows_for_user("rrhh1", ROLE_READER)
    assert [w["name"] for w in visible] == ["Flujo RRHH"]

    assert workflows.list_workflows_for_user("someone_else", ROLE_READER) == []


def test_can_user_run_workflow(isolated_state):
    workflow = workflows.create_workflow("Flujo 1", _STEPS)
    # set_reader_access returns the updated record -- `workflow` itself is a
    # snapshot from before access was granted and must not be reused as-is.
    workflow = workflows.set_reader_access(workflow["id"], ["rrhh1"])

    assert workflows.can_user_run_workflow(workflow, "someop", ROLE_OPERATOR) is True
    assert workflows.can_user_run_workflow(workflow, "someadmin", ROLE_ADMIN) is True
    assert workflows.can_user_run_workflow(workflow, "rrhh1", ROLE_READER) is True
    assert workflows.can_user_run_workflow(workflow, "someone_else", ROLE_READER) is False


def test_list_workflows_for_user_reader_handles_legacy_records_without_the_field(isolated_state):
    """A workflow created before this feature existed has no
    reader_allowed_users key at all -- must not crash, must behave as
    "no reader assigned" rather than raising a KeyError."""
    workflow = workflows.create_workflow("Flujo legado", _STEPS)
    data = workflows._read()
    del data[0]["reader_allowed_users"]
    workflows._write(data)

    assert workflows.list_workflows_for_user("reader1", ROLE_READER) == []
    assert workflows.can_user_run_workflow(workflow, "reader1", ROLE_READER) is False
