# -*- coding: utf-8 -*-
"""
Read/write access to the project's `.env` file for the admin "Claves de
servicio" screen -- lets an admin set BC_CLIENT_SECRET, HUBSPOT_API_KEY,
etc. from the UI instead of hand-editing `.env` on the server.

This only touches `.env` itself via python-dotenv's `set_key`/`dotenv_values`,
which update a single line in place and preserve every comment/blank line
around it -- never a full-file rewrite. Writing a value also mirrors it into
the *current* process's `os.environ` so the change takes effect immediately:
every extraction/upload/pipeline action calls `load_dotenv()` fresh inside
its own subprocess anyway (see src/*_main.py, src/*/push.py), and
src/sync_engine/compare.py does the same in-process -- nothing needs a
server restart, including BC_ENVIRONMENT, since BC's tables.yaml resolves
the `{ENVIRONMENT}` placeholder in each URL fresh on every load rather than
picking a filename once and caching it.

FIELDS below is a curated allowlist, not a generic .env editor -- only these
exact keys can ever be read or written through this module, so a typo or a
crafted request body can never inject or leak an arbitrary environment
variable.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_ENV_PATH = _PROJECT_ROOT / ".env"


@dataclass(frozen=True)
class EnvField:
    key: str
    label: str
    group: str
    secret: bool  # masked by default in the UI -- still readable, just hidden behind "mostrar clave"


FIELDS: List[EnvField] = [
    EnvField("BC_CLIENT_SECRET", "Client Secret", "Business Central", True),
    EnvField("BC_ENVIRONMENT", "Entorno activo (nombre exacto en BC, ej. PRODUCTION / SANDBOX_CADE)", "Business Central", False),
    EnvField("FABRIC_CLIENT_SECRET", "Client Secret", "Fabric OneLake", True),
    EnvField("FABRIC_UPLOAD_ENABLED", "Forzar subida (override de 'enabled')", "Fabric OneLake", False),
    EnvField("FACTORIAL_API_KEY", "API Key", "Factorial HR", True),
    EnvField("VERSION_API_FACTORIAL", "Versión de API", "Factorial HR", False),
    EnvField("FACTORIAL_OVERLAP_DAYS", "Días de solapamiento incremental", "Factorial HR", False),
    EnvField("HUBSPOT_API_KEY", "Private App Token", "HubSpot CRM", True),
    EnvField("CONFIG_FILE", "Ruta de config.json", "General", False),
    EnvField("SMTP_USERNAME", "Usuario SMTP", "Notificaciones", False),
    EnvField("SMTP_PASSWORD", "Contraseña SMTP", "Notificaciones", True),
    EnvField("TAIDY_SUMMARY_PROVIDER", "Proveedor (anthropic / openai / gemini)", "Resumen por IA", False),
    EnvField("ANTHROPIC_API_KEY", "Anthropic API Key", "Resumen por IA", True),
    EnvField("ANTHROPIC_MODEL", "Modelo Anthropic", "Resumen por IA", False),
    EnvField("OPENAI_API_KEY", "OpenAI API Key", "Resumen por IA", True),
    EnvField("OPENAI_MODEL", "Modelo OpenAI", "Resumen por IA", False),
    EnvField("OPENAI_BASE_URL", "OpenAI Base URL (modelo local)", "Resumen por IA", False),
    EnvField("GEMINI_API_KEY", "Gemini API Key", "Resumen por IA", True),
    EnvField("GEMINI_MODEL", "Modelo Gemini", "Resumen por IA", False),
]

_FIELDS_BY_KEY = {f.key: f for f in FIELDS}


def _as_dict(field: EnvField, value: str) -> Dict[str, Any]:
    return {"key": field.key, "label": field.label, "group": field.group, "secret": field.secret, "value": value}


def list_fields() -> List[Dict[str, Any]]:
    """Current value (read straight from `.env` on disk) for every known field, in registry order."""
    values = dotenv.dotenv_values(str(_ENV_PATH)) if _ENV_PATH.is_file() else {}
    return [_as_dict(f, values.get(f.key) or "") for f in FIELDS]


def set_field(key: str, value: str) -> Dict[str, Any]:
    field = _FIELDS_BY_KEY.get(key)
    if field is None:
        raise ValueError(f"'{key}' no es una clave reconocida.")

    if not _ENV_PATH.is_file():
        _ENV_PATH.write_text("", encoding="utf-8")
    dotenv.set_key(str(_ENV_PATH), key, value, quote_mode="always")
    os.environ[key] = value

    return _as_dict(field, value)


# --------------------------------------------------------------------------------------
# "Probar acceso" -- one minimal, strictly read-only call per service. None of
# these ever create, update, or delete anything in BC/Factorial/HubSpot/Fabric;
# each just confirms the current secret actually authenticates.
# --------------------------------------------------------------------------------------


def test_business_central() -> Dict[str, Any]:
    dotenv.load_dotenv(str(_ENV_PATH))
    try:
        from src.bc_client.api import BusinessCentralClient
        from src.bc_client.auth import OAuthTokenProvider
        from src.bc_client.config import load_settings as load_bc_settings

        settings = load_bc_settings()
        if not settings.tables:
            return {"ok": False, "message": "No hay tablas configuradas en tables.yaml para probar."}

        secret = os.environ.get("BC_CLIENT_SECRET", "").strip()
        if not secret:
            return {"ok": False, "message": "Falta BC_CLIENT_SECRET."}

        provider = OAuthTokenProvider(
            token_url=settings.token_url, client_id=settings.client_id, client_secret=secret, scope=settings.scope
        )
        client = BusinessCentralClient(settings=settings, token_provider=provider)
        table = settings.tables[0]
        separator = "&" if "?" in table.url else "?"
        rows = client.get_table_rows(f"{table.url}{separator}$top=1", label=table.name)
        return {"ok": True, "message": f"Conectado correctamente. Leída la tabla '{table.name}' ({len(rows)} fila(s))."}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


def test_factorial() -> Dict[str, Any]:
    dotenv.load_dotenv(str(_ENV_PATH))
    try:
        from datetime import date

        from src.factorial_client.api import FactorialClient
        from src.factorial_client.config import load_settings as load_factorial_settings

        settings = load_factorial_settings()
        if not settings.tables:
            return {"ok": False, "message": "No hay tablas configuradas en factorial_tables.yaml para probar."}

        client = FactorialClient(settings=settings)
        # Prefer a table that needs neither employee_ids nor a date range --
        # this is just a connectivity check, not a real extraction, and most
        # tables require at least one of those to return anything.
        table = next(
            (t for t in settings.tables if not t.employee_filter and not t.date_range), settings.tables[0]
        )
        today = date.today().isoformat()
        rows = client.fetch_table(table, start_on=today, end_on=today)
        return {"ok": True, "message": f"Conectado correctamente. Leída la tabla '{table.name}' ({len(rows)} fila(s))."}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


def test_hubspot() -> Dict[str, Any]:
    dotenv.load_dotenv(str(_ENV_PATH))
    try:
        from src.hubspot_client.api import HubspotClient
        from src.hubspot_client.config import load_settings as load_hubspot_settings

        settings = load_hubspot_settings()
        client = HubspotClient(settings=settings)
        payload = client.ping()
        count = len(payload.get("results", []))
        return {"ok": True, "message": f"Conectado correctamente. HubSpot devolvió {count} contacto(s)."}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


def test_fabric() -> Dict[str, Any]:
    dotenv.load_dotenv(str(_ENV_PATH))
    try:
        from azure.core.exceptions import HttpResponseError, ResourceNotFoundError

        from src.fabric_upload.client_factory import create_file_system_client
        from src.fabric_upload.config import load_fabric_settings

        settings = load_fabric_settings(_PROJECT_ROOT, force_enable=True)
        if settings is None:
            return {"ok": False, "message": "La subida a Fabric está desactivada y no se pudo forzar."}

        file_system = create_file_system_client(settings)
        try:
            # Same "list, don't assume .exists() is reliable" approach
            # src/fabric_upload/uploader.py's own _file_exists() uses for
            # per-file checks -- OneLake doesn't always answer a generic
            # filesystem-level exists() the way plain ADLS Gen2 does.
            next(iter(file_system.get_paths(max_results=1)), None)
            return {"ok": True, "message": "Conectado correctamente. Se pudo listar el filesystem 'Files'."}
        except (ResourceNotFoundError, HttpResponseError) as exc:
            status = getattr(exc, "status_code", None)
            if status in (400, 404):
                return {
                    "ok": True,
                    "message": (
                        "Autenticación correcta, pero no se encontró el filesystem 'Files' "
                        "(revisa el workspace/lakehouse configurados)."
                    ),
                }
            raise
    except Exception as exc:
        return {"ok": False, "message": str(exc)}
