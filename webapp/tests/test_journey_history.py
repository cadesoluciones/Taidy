# -*- coding: utf-8 -*-
"""
Journey 3 (audit §4): "quiero saber si el flujo de anoche falló y por qué."

Seeds a realistic mix of history entries (including one failed run) and
drives the real filters added in Fase 6 (ND-08) to isolate it, then opens its
log -- exactly the recorrido the audit (H-08) called out as degrading without
filters as history grows.
"""

from __future__ import annotations

from streamlit.testing.v1 import AppTest

from webapp import history, users_db
from webapp.tests import _page_scripts


def test_can_filter_history_to_the_failed_run(isolated_state):
    history.record_run(
        action="sync_factorial",
        source="programada: nightly",
        status="ok",
        ok=True,
        message="Completado correctamente.",
        log="",
        duration_seconds=42.0,
    )
    history.record_run(
        action="sync_factorial",
        source="programada: nightly",
        status="error",
        ok=False,
        message="Terminó con código de salida 1. Revisa el log.",
        log="Traceback...\nRuntimeError: connection refused",
        duration_seconds=3.5,
    )
    history.record_run(
        action="extract_bc",
        source="admin",
        status="ok",
        ok=True,
        message="Completado correctamente.",
        log="",
        duration_seconds=8.0,
    )

    at = AppTest.from_function(_page_scripts.run_page_history)
    at.session_state["auth_user"] = {"username": "admin", "role": users_db.ROLE_ADMIN}
    at.run(timeout=15)
    assert not at.exception
    assert any("Mostrando 3 de 3" in c.value for c in at.caption)

    at.selectbox(key="hist_f_result").set_value("Error")
    at.run(timeout=15)
    assert not at.exception
    assert any("Mostrando 1 de 3" in c.value for c in at.caption)
    assert any("❌" in m.value for m in at.markdown)

    log_expanders = [e for e in at.expander if e.label == "Ver log"]
    assert len(log_expanders) == 1
