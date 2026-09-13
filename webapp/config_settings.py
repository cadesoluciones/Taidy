# -*- coding: utf-8 -*-
"""
Read/write access to the project's `config.json` for the admin "Claves de
servicio" screen -- lets an admin change tenant/client/workspace/lakehouse
ids, retry/paging tuning, notification settings, and Fabric pipeline
mappings from the UI instead of hand-editing config.json on the server (or
in git -- it's tracked, with real tenant/client/workspace ids baked in).

Mirrors webapp/env_secrets.py's pattern (a curated field registry, write-
in-place never a rename onto the target -- see _write() below) but for a
nested JSON tree instead of flat KEY=VALUE lines, and several fields that
are genuinely ONE value duplicated across multiple config.json sections
today (see SHARED FIELDS below) rather than one value per key.

FIELDS is a curated allowlist, not a generic config.json editor -- only
these exact (section, key) pairs can ever be read or written through this
module. Deliberately excluded (see PR/commit message for the full
reasoning): fields that are platform constants identical for every tenant
of that SaaS (business_central.scope, factorial.base_url, hubspot.base_url),
business_central.token_url (derived from tenant_id, see below -- never
independently editable), and internal folder-naming/wiring conventions
that downstream bronze notebooks and the table-config UI already depend on
(tables_file, output_dir, path_prefix, source_name, checkpoint_path).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union

from src.config_loader import load_config_data

FieldValue = Union[str, int, bool, List[str]]


def _config_path() -> Path:
    """Same resolution as src.config_loader.load_config_data(None) --
    CONFIG_FILE env var, else config.json in the current directory."""
    return Path(os.environ.get("CONFIG_FILE", "config.json")).expanduser().resolve()


def _read() -> Dict[str, Any]:
    data, _root = load_config_data(None)
    return data


def _write(data: Dict[str, Any]) -> None:
    """Overwrites config.json wholesale. Deliberately NOT a tmp-file +
    os.replace() rename onto the real path -- config.json is bind-mounted
    read-write from the host in docker-compose.yml specifically so this
    can work, and (like webapp/env_secrets.py's .env writes) a rename onto
    a single-file Docker bind mount fails with "Device or resource busy".
    Building the full JSON text in memory first and writing it in one
    shot keeps the window for a torn/partial write as small as reasonably
    possible without that rename."""
    text = _dumps(data)
    _config_path().write_bytes(text.encode("utf-8"))


def _dumps(data: Dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


@dataclass(frozen=True)
class ConfigField:
    key: str
    label: str
    group: str
    kind: str  # "text" | "number" | "boolean" | "list"
    # One or more (section, json_key) pairs to read/write TOGETHER -- more
    # than one entry means this is really a single logical value that
    # today happens to be duplicated across several config.json sections
    # (e.g. the same Fabric workspace/lakehouse used by all three of
    # business_central_upload/factorial_upload/hubspot_upload). Read uses
    # the first pair; save writes the same value into every pair, so the
    # copies can never drift apart from each other again.
    paths: Tuple[Tuple[str, str], ...]


# Shared by every "*_upload" section -- confirmed identical across all
# three in this workspace's own config.json (one Azure AD app + one
# workspace/lakehouse used for every Fabric OneLake upload), and
# src/fabric_pipelines/config.py already documents reusing
# business_central_upload's credentials for pipeline triggers too.
_UPLOAD_SECTIONS = ("business_central_upload", "factorial_upload", "hubspot_upload")


def _upload_paths(json_key: str) -> Tuple[Tuple[str, str], ...]:
    return tuple((section, json_key) for section in _UPLOAD_SECTIONS)


FIELDS: List[ConfigField] = [
    # --- Business Central (extracción vía OData) ---
    ConfigField("bc_tenant_id", "Id. de inquilino (tenant)", "Business Central", "text", (("business_central", "tenant_id"),)),
    ConfigField(
        "bc_client_id", "Id. de aplicación (cliente)", "Business Central", "text", (("business_central", "client_id"),)
    ),
    ConfigField(
        "bc_company_name",
        "Nombre de la empresa (filtro OData)",
        "Business Central",
        "text",
        (("business_central", "company_name"),),
    ),
    ConfigField(
        "bc_page_size", "Tamaño de página (paginación OData)", "Business Central", "number", (("business_central", "page_size"),)
    ),
    # --- Fabric OneLake (subida -- compartido por BC/Factorial/HubSpot) ---
    ConfigField("fabric_upload_tenant_id", "Id. de inquilino (tenant)", "Fabric OneLake", "text", _upload_paths("tenant_id")),
    ConfigField(
        "fabric_upload_client_id", "Id. de aplicación (cliente)", "Fabric OneLake", "text", _upload_paths("client_id")
    ),
    ConfigField("fabric_upload_workspace_id", "Id. del workspace", "Fabric OneLake", "text", _upload_paths("workspace_id")),
    ConfigField(
        "fabric_upload_workspace_name", "Nombre del workspace", "Fabric OneLake", "text", _upload_paths("workspace_name")
    ),
    ConfigField("fabric_upload_lakehouse_id", "Id. del Lakehouse", "Fabric OneLake", "text", _upload_paths("lakehouse_id")),
    ConfigField(
        "fabric_upload_lakehouse_name", "Nombre del Lakehouse", "Fabric OneLake", "text", _upload_paths("lakehouse_name")
    ),
    ConfigField(
        "fabric_upload_max_retries",
        "Reintentos ante fallo de subida",
        "Fabric OneLake",
        "number",
        _upload_paths("max_retries"),
    ),
    # Only business_central_upload's own uploader (src/fabric_upload/config.py)
    # actually reads "enabled"/"overwrite" -- Factorial/HubSpot's push CLIs
    # have no config-driven equivalent (confirmed in src/factorial_client/push.py
    # and src/hubspot_client/push.py), so these two stay BC-only, unlike
    # every other field in this group.
    ConfigField(
        "fabric_upload_enabled",
        "Subida automática habilitada (Business Central)",
        "Fabric OneLake",
        "boolean",
        (("business_central_upload", "enabled"),),
    ),
    ConfigField(
        "fabric_upload_overwrite",
        "Sobrescribir ficheros existentes (Business Central)",
        "Fabric OneLake",
        "boolean",
        (("business_central_upload", "overwrite"),),
    ),
    # --- Notificaciones ---
    ConfigField("notifications_enabled", "Avisos por email activados", "Notificaciones", "boolean", (("notifications", "enabled"),)),
    ConfigField("notifications_smtp_host", "Servidor SMTP", "Notificaciones", "text", (("notifications", "smtp_host"),)),
    ConfigField("notifications_smtp_port", "Puerto SMTP", "Notificaciones", "number", (("notifications", "smtp_port"),)),
    ConfigField("notifications_use_tls", "Usar TLS", "Notificaciones", "boolean", (("notifications", "use_tls"),)),
    ConfigField(
        "notifications_from_address", "Dirección remitente", "Notificaciones", "text", (("notifications", "from_address"),)
    ),
    ConfigField(
        "notifications_admin_recipients",
        "Destinatarios de aviso",
        "Notificaciones",
        "list",
        (("notifications", "admin_recipients"),),
    ),
]

_FIELDS_BY_KEY = {f.key: f for f in FIELDS}

# business_central.token_url is entirely derived from tenant_id (it's
# literally the same tenant_id interpolated into Microsoft's own OAuth
# token endpoint URL) -- keeping it as an independently-stored, never-
# recomputed value meant a tenant migration could silently leave it
# pointing at the OLD tenant while everything else moved to the new one,
# failing every BC OAuth call with a confusing "invalid_client"-style
# error instead of an obvious "your tenant id looks wrong". Recomputed
# here as a side effect of saving bc_tenant_id, never editable on its own.
_BC_TOKEN_URL_TEMPLATE = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"


def _get_value(field: ConfigField, data: Dict[str, Any]) -> FieldValue:
    section, json_key = field.paths[0]
    raw = data.get(section, {}).get(json_key)
    if field.kind == "boolean":
        return bool(raw)
    if field.kind == "number":
        return int(raw) if raw is not None else 0
    if field.kind == "list":
        return [str(v) for v in raw] if isinstance(raw, list) else []
    return str(raw) if raw is not None else ""


def _as_dict(field: ConfigField, value: FieldValue) -> Dict[str, Any]:
    return {"key": field.key, "label": field.label, "group": field.group, "kind": field.kind, "value": value}


def list_fields() -> List[Dict[str, Any]]:
    """Current value (read straight from config.json on disk) for every
    known field, in registry order."""
    data = _read()
    return [_as_dict(f, _get_value(f, data)) for f in FIELDS]


def _parse_value(field: ConfigField, value: FieldValue) -> FieldValue:
    if field.kind == "boolean":
        return bool(value)
    if field.kind == "number":
        try:
            return int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            raise ValueError(f"'{field.label}' debe ser un número entero.") from exc
    if field.kind == "list":
        if not isinstance(value, list):
            raise ValueError(f"'{field.label}' debe ser una lista de valores.")
        seen: List[str] = []
        for v in value:
            cleaned = str(v).strip()
            if cleaned and cleaned not in seen:
                seen.append(cleaned)
        return seen
    return str(value).strip()


def set_field(key: str, value: FieldValue) -> Dict[str, Any]:
    field = _FIELDS_BY_KEY.get(key)
    if field is None:
        raise ValueError(f"'{key}' no es una clave reconocida.")
    parsed = _parse_value(field, value)

    data = _read()
    for section, json_key in field.paths:
        data.setdefault(section, {})[json_key] = parsed
    if key == "bc_tenant_id":
        data.setdefault("business_central", {})["token_url"] = _BC_TOKEN_URL_TEMPLATE.format(tenant_id=parsed)
    _write(data)

    return _as_dict(field, parsed)


# --------------------------------------------------------------------------------------
# Fabric pipelines (fabric_pipelines.pipelines): a list of {name, item_id},
# not a scalar -- kept separate from the FIELDS registry above the same
# way BC/Factorial/HubSpot's own table lists get a dedicated manager
# instead of being crammed into a flat field list.
# --------------------------------------------------------------------------------------


def list_pipelines() -> List[Dict[str, str]]:
    data = _read()
    section = data.get("fabric_pipelines")
    if not isinstance(section, dict):
        return []
    raw = section.get("pipelines")
    return [{"name": str(p.get("name", "")), "item_id": str(p.get("item_id", ""))} for p in raw] if isinstance(raw, list) else []


def set_pipelines(pipelines: List[Dict[str, str]]) -> List[Dict[str, str]]:
    cleaned: List[Dict[str, str]] = []
    seen_names: List[str] = []
    for entry in pipelines:
        name = str(entry.get("name", "")).strip()
        item_id = str(entry.get("item_id", "")).strip()
        if not name or not item_id:
            raise ValueError("Cada pipeline necesita un nombre y un item_id.")
        if name in seen_names:
            raise ValueError(f"Nombre de pipeline repetido: '{name}'.")
        seen_names.append(name)
        cleaned.append({"name": name, "item_id": item_id})

    data = _read()
    data.setdefault("fabric_pipelines", {})["pipelines"] = cleaned
    _write(data)
    return cleaned
