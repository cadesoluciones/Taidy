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


_ICON_KEYS = {"database", "table", "file", "pipeline", "warehouse", "boxes"}


def test_get_type_icons_returns_the_built_in_defaults_untouched(isolated_state):
    icons = app_settings.get_type_icons()
    assert icons["Lakehouse"] == "database"
    assert icons["Tabla"] == "table"


def test_set_type_icon_overrides_a_built_in_default(isolated_state):
    icons = app_settings.set_type_icon("Lakehouse", "boxes", valid_icon_keys=_ICON_KEYS)
    assert icons["Lakehouse"] == "boxes"
    assert app_settings.get_type_icons()["Lakehouse"] == "boxes"


def test_set_type_icon_adds_a_default_for_a_type_with_none_yet(isolated_state):
    icons = app_settings.set_type_icon("Environment", "cloud", valid_icon_keys=_ICON_KEYS | {"cloud"})
    assert icons["Environment"] == "cloud"


def test_set_type_icon_empty_string_clears_an_override_back_to_the_built_in_default(isolated_state):
    app_settings.set_type_icon("Lakehouse", "boxes", valid_icon_keys=_ICON_KEYS)
    icons = app_settings.set_type_icon("Lakehouse", "", valid_icon_keys=_ICON_KEYS)
    assert icons["Lakehouse"] == "database"  # back to the built-in default


def test_set_type_icon_rejects_an_unknown_icon_key(isolated_state):
    with pytest.raises(ValueError, match="desconocido"):
        app_settings.set_type_icon("Lakehouse", "not-a-real-icon", valid_icon_keys=_ICON_KEYS)
    assert app_settings.get_type_icons()["Lakehouse"] == "database"


def test_set_type_icon_rejects_a_blank_type_name(isolated_state):
    with pytest.raises(ValueError, match="vacío"):
        app_settings.set_type_icon("   ", "database", valid_icon_keys=_ICON_KEYS)
