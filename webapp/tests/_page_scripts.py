# -*- coding: utf-8 -*-
"""
Top-level entry points passed to `streamlit.testing.v1.AppTest.from_function`.

AppTest extracts a function's source via `inspect.getsourcelines` and re-execs
it standalone -- it does NOT capture closures, so these must stay plain,
self-contained module-level functions (no fixtures, no outer variables). Each
test sets `at.session_state["auth_user"]` before the first `.run()`; the
`setdefault` below is just a convenience fallback for scripts run without that.
"""

from __future__ import annotations


def run_page_bc_sync() -> None:
    import streamlit as st
    from webapp import app as app_module

    st.session_state.setdefault("auth_user", {"username": "admin", "role": "App.Admin"})
    app_module.page_bc_sync()


def run_page_running() -> None:
    import streamlit as st
    from webapp import app as app_module

    st.session_state.setdefault("auth_user", {"username": "admin", "role": "App.Admin"})
    app_module.page_running()


def run_page_users() -> None:
    import streamlit as st
    from webapp import app as app_module

    st.session_state.setdefault("auth_user", {"username": "admin", "role": "App.Admin"})
    app_module.page_users()


def run_page_history() -> None:
    import streamlit as st
    from webapp import app as app_module

    st.session_state.setdefault("auth_user", {"username": "admin", "role": "App.Admin"})
    app_module.page_history()
