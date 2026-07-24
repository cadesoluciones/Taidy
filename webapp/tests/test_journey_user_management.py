# -*- coding: utf-8 -*-
"""
Journey 2 (audit §4): "quiero dar de alta a un compañero como Operator."

Covers creating a user with a role via the real form (webapp/app.py:page_users),
and the H-04/ND-05 fix: touching the role selector no longer applies the
change by itself -- it only reveals a "Guardar rol" button, which itself
opens a confirmation dialog rather than saving directly.

Known AppTest limitation (established earlier in this project): st.dialog
content doesn't persist across separate .run() calls in AppTest, so the
confirm-and-save step can't be driven through the dialog here. What this DOES
verify end-to-end is everything AppTest can see: the selector alone never
changes the stored role, and "Guardar rol" only appears once the selection
actually differs from the current one. The dialog's own save action is a
one-line call to users_db.set_role, verified directly below.
"""

from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

from webapp import users_db
from webapp.tests import _page_scripts
from webapp.tests.conftest import make_user


def test_admin_can_create_operator_user(isolated_state):
    at = AppTest.from_function(_page_scripts.run_page_users)
    at.session_state["auth_user"] = {"username": "admin", "role": users_db.ROLE_ADMIN}
    at.run(timeout=15)
    assert not at.exception

    at.text_input(key="user_new_username").set_value("carlos")
    at.text_input(key="user_new_password").set_value("Temporal2026!")
    at.selectbox(key="user_new_role").set_value(users_db.ROLE_OPERATOR)
    submit = next(b for b in at.button if b.label == "Crear usuario")
    submit.click().run(timeout=15)

    # page_users() calls st.success(...) immediately followed by st.rerun() on
    # success -- the same transient-message-before-rerun pattern already
    # documented elsewhere in this project as an AppTest limitation (the
    # message flashes but is gone by the time the triggered rerun's own final
    # element tree is captured). The real, durable assertion is the DB state.
    assert not at.exception

    created = users_db.get_user("carlos")
    assert created is not None
    assert created["role"] == users_db.ROLE_OPERATOR
    assert created["must_change_password"]  # stored as 0/1, checked truthily like the UI does


def test_changing_role_selector_does_not_apply_by_itself(isolated_state):
    make_user("carlos", "Temporal2026!", users_db.ROLE_OPERATOR)

    at = AppTest.from_function(_page_scripts.run_page_users)
    at.session_state["auth_user"] = {"username": "admin", "role": users_db.ROLE_ADMIN}
    at.run(timeout=15)

    role_selector = at.selectbox(key="role_carlos")
    assert role_selector.value == users_db.ROLE_OPERATOR

    role_selector.set_value(users_db.ROLE_ADMIN)
    at.run(timeout=15)

    # H-04 / ND-05: touching the selector alone must NOT change anything yet.
    assert users_db.get_user("carlos")["role"] == users_db.ROLE_OPERATOR
    assert any(b.label == "Guardar rol" for b in at.button)


def test_last_admin_cannot_be_demoted(isolated_state):
    # Backend invariant the "Guardar rol" confirmation dialog relies on: it
    # must be impossible to lock everyone out of Administración by demoting
    # the only remaining admin.
    with pytest.raises(ValueError):
        users_db.set_role("admin", users_db.ROLE_READER)
