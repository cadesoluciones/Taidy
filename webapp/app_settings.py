# -*- coding: utf-8 -*-
"""
Small persisted store for app-wide (not per-user) settings -- currently just
which mode ("template" | "llm") generates Inicio's "resumen de actividad".
Same read-fresh/write-through JSON-file pattern as every other webapp/*.py
store (webapp/scheduler.py, workflows.py, history.py, ...).
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Dict

from webapp.state_dir import state_path

_SETTINGS_PATH = state_path("app_settings.json", Path(__file__).resolve().parent)
_LOCK = threading.Lock()

SUMMARY_MODE_TEMPLATE = "template"
SUMMARY_MODE_LLM = "llm"
VALID_SUMMARY_MODES = {SUMMARY_MODE_TEMPLATE, SUMMARY_MODE_LLM}


def _read() -> Dict:
    if not _SETTINGS_PATH.exists():
        return {}
    try:
        data = json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write(data: Dict) -> None:
    tmp = _SETTINGS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(_SETTINGS_PATH)


def get_summary_mode() -> str:
    with _LOCK:
        return _read().get("summary_mode", SUMMARY_MODE_TEMPLATE)


def set_summary_mode(mode: str) -> str:
    if mode not in VALID_SUMMARY_MODES:
        raise ValueError(f"Modo de resumen desconocido: '{mode}'. Debe ser 'template' o 'llm'.")
    with _LOCK:
        data = _read()
        data["summary_mode"] = mode
        _write(data)
    return mode
