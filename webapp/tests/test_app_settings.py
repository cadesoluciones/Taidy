# -*- coding: utf-8 -*-
"""app_settings.py currently holds one setting: which mode generates Inicio's
"resumen de actividad" -- an app-wide Admin choice, not a per-user one."""

from __future__ import annotations

import pytest

from webapp import app_settings


def test_summary_mode_defaults_to_template(isolated_state):
    assert app_settings.get_summary_mode() == "template"


def test_set_summary_mode_persists(isolated_state):
    app_settings.set_summary_mode("llm")

    assert app_settings.get_summary_mode() == "llm"


def test_set_summary_mode_rejects_an_unknown_value(isolated_state):
    with pytest.raises(ValueError, match="desconocido"):
        app_settings.set_summary_mode("not-a-real-mode")

    # Rejected write must not have touched the stored value.
    assert app_settings.get_summary_mode() == "template"


def test_set_summary_mode_back_to_template(isolated_state):
    app_settings.set_summary_mode("llm")
    app_settings.set_summary_mode("template")

    assert app_settings.get_summary_mode() == "template"
