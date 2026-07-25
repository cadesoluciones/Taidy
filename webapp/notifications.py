# -*- coding: utf-8 -*-
"""
Best-effort email notifications on task/workflow completion.

Explicit opt-in per launch (never sent unless the caller/scheduled entry
asks for it, via the `notify` flag threaded through webapp/tasks.py and
webapp/workflow_engine.py), to a fixed admin distribution list -- not
per-user addresses, per the project owner's own decision (see
ARCHITECTURE.md). SMTP credentials live in .env/config.json like every
other secret this project uses (Business Central, Factorial, Fabric),
never in the UI or in git.

A notification failure must never break the task pipeline: every public
function here catches its own exceptions and logs them, matching the same
"never raises" contract webapp/adapter.py's config_defaults() already uses.
"""

from __future__ import annotations

import logging
import os
import smtplib
import sys
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Callable, List, Optional

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.config_loader import load_config_data  # noqa: E402

logger = logging.getLogger("taidy.notifications")

SenderFn = Callable[[EmailMessage], None]

_STATUS_LABELS = {"ok": "Completada correctamente", "error": "Error", "stopped": "Detenida"}


@dataclass
class NotificationSettings:
    smtp_host: str
    smtp_port: int
    use_tls: bool
    smtp_username: str
    smtp_password: str
    from_address: str
    admin_recipients: List[str]


def load_notification_settings() -> Optional[NotificationSettings]:
    """Best-effort read of config.json's `notifications` section plus
    SMTP_USERNAME/SMTP_PASSWORD from the environment. Returns None (never
    raises) if the feature isn't configured, disabled, or missing a
    required field -- callers treat that exactly like "notifications are
    off", never as an error that should interrupt anything.
    """
    try:
        data, _root = load_config_data()
    except Exception:
        return None

    section = data.get("notifications")
    if not isinstance(section, dict) or not section.get("enabled"):
        return None

    recipients = section.get("admin_recipients") or []
    host = section.get("smtp_host") or ""
    from_address = section.get("from_address") or ""
    if not (host and from_address and recipients):
        logger.warning(
            "notifications.enabled=true en config.json pero falta smtp_host, "
            "from_address o admin_recipients; se omiten los avisos."
        )
        return None

    return NotificationSettings(
        smtp_host=host,
        smtp_port=int(section.get("smtp_port", 587)),
        use_tls=bool(section.get("use_tls", True)),
        smtp_username=os.environ.get("SMTP_USERNAME", ""),
        smtp_password=os.environ.get("SMTP_PASSWORD", ""),
        from_address=from_address,
        admin_recipients=list(recipients),
    )


def _default_sender(settings: NotificationSettings) -> SenderFn:
    def _send(message: EmailMessage) -> None:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            if settings.use_tls:
                smtp.starttls()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)

    return _send


def _send_notification(subject: str, body: str, *, sender: Optional[SenderFn] = None) -> None:
    settings = load_notification_settings()
    if settings is None:
        return

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.from_address
    message["To"] = ", ".join(settings.admin_recipients)
    message.set_content(body)

    try:
        (sender or _default_sender(settings))(message)
    except Exception:
        logger.exception("No se pudo enviar la notificación por email: %s", subject)


def notify_task_finished(
    *,
    action_label: str,
    triggered_by: str,
    status: str,
    message: str,
    sender: Optional[SenderFn] = None,
) -> None:
    label = _STATUS_LABELS.get(status, status)
    subject = f"Taidy · {action_label}: {label}"
    body = f"Tarea: {action_label}\nLanzada por: {triggered_by}\nEstado: {label}\n\n{message}\n"
    _send_notification(subject, body, sender=sender)


def notify_workflow_finished(
    *,
    workflow_name: str,
    triggered_by: str,
    status: str,
    message: str,
    sender: Optional[SenderFn] = None,
) -> None:
    label = _STATUS_LABELS.get(status, status)
    subject = f"Taidy · Flujo '{workflow_name}': {label}"
    body = f"Flujo: {workflow_name}\nLanzado por: {triggered_by}\nEstado: {label}\n\n{message}\n"
    _send_notification(subject, body, sender=sender)
