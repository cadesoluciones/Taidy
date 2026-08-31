# -*- coding: utf-8 -*-
"""
Small persisted store for app-wide (not per-user) settings -- which mode
("template" | "llm") generates Inicio's "resumen de actividad", and which
icon (see webapp.fabric_catalog.ICON_KEYS) is the default for each Fabric
catalog item type, when an item hasn't had one set by hand. Same
read-fresh/write-through JSON-file pattern as every other webapp/*.py store
(webapp/scheduler.py, workflows.py, history.py, ...).
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

# A sensible starting point per Fabric item type (see webapp/fabric_catalog.py's
# ICON_KEYS for the full palette) -- shown until an admin overrides one in
# Configuración, or an item gets its own icon by hand. Anything not listed
# here (a Fabric item type this tenant doesn't use yet, or a brand new one)
# just has no default -- the UI falls back to a generic placeholder rather
# than guessing.
DEFAULT_TYPE_ICONS: Dict[str, str] = {
    "Notebook": "file",
    "DataPipeline": "pipeline",
    "Lakehouse": "database",
    "Warehouse": "warehouse",
    "Report": "chart",
    "SemanticModel": "boxes",
    "Environment": "cloud",
    "SQLEndpoint": "external",
    "Tabla": "table",
    "Personalizado": "manual",
}


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


def get_type_icons() -> Dict[str, str]:
    """DEFAULT_TYPE_ICONS with any admin overrides/additions from
    app_settings.json layered on top -- a type an admin has never touched
    still gets the built-in default instead of nothing."""
    with _LOCK:
        stored = _read().get("type_icons", {})
    merged = dict(DEFAULT_TYPE_ICONS)
    if isinstance(stored, dict):
        merged.update({k: v for k, v in stored.items() if isinstance(k, str) and isinstance(v, str)})
    return merged


def set_type_icon(item_type: str, icon: str, *, valid_icon_keys: "set[str]") -> Dict[str, str]:
    """Sets (or, with icon="", clears back to the built-in default/no
    default) one item type's default icon. `valid_icon_keys` is passed in
    (ICON_KEYS from webapp.fabric_catalog) rather than imported at module
    level to avoid a hard dependency between the two stores for what's
    really just a shared validation set."""
    item_type = item_type.strip()
    if not item_type:
        raise ValueError("El tipo de elemento no puede estar vacío.")
    if icon and icon not in valid_icon_keys:
        raise ValueError(f"Icono desconocido: {icon!r}")
    with _LOCK:
        data = _read()
        stored = data.get("type_icons", {})
        if not isinstance(stored, dict):
            stored = {}
        if icon:
            stored[item_type] = icon
        else:
            stored.pop(item_type, None)
        data["type_icons"] = stored
        _write(data)
    merged = dict(DEFAULT_TYPE_ICONS)
    merged.update(stored)
    return merged
