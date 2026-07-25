# -*- coding: utf-8 -*-
"""
NEW-01: opt-in email notifications on task/workflow completion.

Covers webapp/notifications.py in isolation (never touches the real
config.json or a real SMTP server -- every test either supplies its own
config dict via monkeypatch or an injected `sender` callable) and the
`notify` flag plumbing through webapp/tasks.py and webapp/workflow_engine.py.
"""

from __future__ import annotations

import time

from webapp import notifications, tasks, workflow_engine, workflows
from webapp.tests.conftest import make_user
from webapp import users_db


def _wait_until_finished(task_id: str, timeout: float = 10.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        task = tasks.get_task(task_id)
        if task is not None and task.status in ("ok", "error", "stopped"):
            return
        time.sleep(0.05)


def _wait_until_run_finished(run_id: str, timeout: float = 10.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = workflow_engine.get_run(run_id)
        if run is not None and run.status != "running":
            return
        time.sleep(0.05)


def _wait_until(predicate, timeout: float = 5.0) -> None:
    """Polls `predicate()` -- used for side effects (like a notification call)
    that land a moment after a task/run's status flips to terminal, since
    _finalize() sets .status before running its trailing side effects."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.05)


# --------------------------------------------------------------------------------------
# load_notification_settings()
# --------------------------------------------------------------------------------------


def test_load_settings_returns_none_when_section_missing(monkeypatch):
    monkeypatch.setattr(notifications, "load_config_data", lambda: ({}, None))
    assert notifications.load_notification_settings() is None


def test_load_settings_returns_none_when_disabled(monkeypatch):
    monkeypatch.setattr(
        notifications,
        "load_config_data",
        lambda: ({"notifications": {"enabled": False}}, None),
    )
    assert notifications.load_notification_settings() is None


def test_load_settings_returns_none_when_missing_required_fields(monkeypatch):
    monkeypatch.setattr(
        notifications,
        "load_config_data",
        lambda: ({"notifications": {"enabled": True, "smtp_host": "smtp.test"}}, None),
    )
    assert notifications.load_notification_settings() is None


def test_load_settings_returns_populated_settings(monkeypatch):
    monkeypatch.setenv("SMTP_USERNAME", "bot")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setattr(
        notifications,
        "load_config_data",
        lambda: (
            {
                "notifications": {
                    "enabled": True,
                    "smtp_host": "smtp.test",
                    "smtp_port": 2525,
                    "use_tls": False,
                    "from_address": "taidy@test.com",
                    "admin_recipients": ["admin@test.com"],
                }
            },
            None,
        ),
    )
    settings = notifications.load_notification_settings()
    assert settings is not None
    assert settings.smtp_host == "smtp.test"
    assert settings.smtp_port == 2525
    assert settings.use_tls is False
    assert settings.from_address == "taidy@test.com"
    assert settings.admin_recipients == ["admin@test.com"]
    assert settings.smtp_username == "bot"
    assert settings.smtp_password == "secret"


def test_load_settings_never_raises_on_bad_config(monkeypatch):
    def _boom():
        raise ValueError("malformed config.json")

    monkeypatch.setattr(notifications, "load_config_data", _boom)
    assert notifications.load_notification_settings() is None


# --------------------------------------------------------------------------------------
# _send_notification() / notify_task_finished() / notify_workflow_finished()
# --------------------------------------------------------------------------------------


def _enable_settings(monkeypatch, **overrides):
    section = {
        "enabled": True,
        "smtp_host": "smtp.test",
        "smtp_port": 587,
        "use_tls": True,
        "from_address": "taidy@test.com",
        "admin_recipients": ["admin1@test.com", "admin2@test.com"],
    }
    section.update(overrides)
    monkeypatch.setattr(notifications, "load_config_data", lambda: ({"notifications": section}, None))


def test_notify_task_finished_calls_injected_sender(monkeypatch):
    _enable_settings(monkeypatch)
    sent = []
    notifications.notify_task_finished(
        action_label="BC · Extraer",
        triggered_by="operator1",
        status="ok",
        message="Completado correctamente.",
        sender=lambda message: sent.append(message),
    )
    assert len(sent) == 1
    message = sent[0]
    assert "BC · Extraer" in message["Subject"]
    assert "Completada correctamente" in message["Subject"]
    assert message["From"] == "taidy@test.com"
    assert message["To"] == "admin1@test.com, admin2@test.com"
    assert "operator1" in message.get_content()


def test_notify_workflow_finished_calls_injected_sender(monkeypatch):
    _enable_settings(monkeypatch)
    sent = []
    notifications.notify_workflow_finished(
        workflow_name="Cierre diario",
        triggered_by="admin",
        status="error",
        message="Terminó con código de salida 1.",
        sender=lambda message: sent.append(message),
    )
    assert len(sent) == 1
    assert "Cierre diario" in sent[0]["Subject"]
    assert "Error" in sent[0]["Subject"]


def test_notification_disabled_never_calls_sender(monkeypatch):
    monkeypatch.setattr(notifications, "load_config_data", lambda: ({}, None))
    sent = []
    notifications.notify_task_finished(
        action_label="BC · Extraer",
        triggered_by="operator1",
        status="ok",
        message="Completado correctamente.",
        sender=lambda message: sent.append(message),
    )
    assert sent == []


def test_sender_failure_is_swallowed_not_raised(monkeypatch):
    _enable_settings(monkeypatch)

    def _boom(message):
        raise OSError("connection refused")

    # Must not raise -- a broken mail server can never break a task/workflow.
    notifications.notify_task_finished(
        action_label="BC · Extraer",
        triggered_by="operator1",
        status="ok",
        message="Completado correctamente.",
        sender=_boom,
    )


# --------------------------------------------------------------------------------------
# notify flag plumbing: webapp/tasks.py
# --------------------------------------------------------------------------------------


def test_launch_with_notify_flag_sends_notification_on_finish(isolated_state, fake_subprocess, monkeypatch):
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    calls = []
    monkeypatch.setattr(
        notifications,
        "notify_task_finished",
        lambda **kwargs: calls.append(kwargs),
    )

    task = tasks.launch("upload_bc", {"notify": True}, "operator1")
    assert task.notify is True

    _wait_until_finished(task.id)
    assert task.status == "ok"
    _wait_until(lambda: len(calls) == 1)
    assert len(calls) == 1
    assert calls[0]["status"] == "ok"
    assert calls[0]["triggered_by"] == "operator1"


def test_launch_without_notify_flag_never_sends_notification(isolated_state, fake_subprocess, monkeypatch):
    make_user("operator1", "OperatorPass2026!", users_db.ROLE_OPERATOR)
    calls = []
    monkeypatch.setattr(
        notifications,
        "notify_task_finished",
        lambda **kwargs: calls.append(kwargs),
    )

    task = tasks.launch("upload_bc", {}, "operator1")
    assert task.notify is False

    _wait_until_finished(task.id)
    assert calls == []


def test_notify_flag_is_stripped_before_reaching_argv_builder(isolated_state, fake_subprocess):
    """A raw 'notify' key must never reach adapter.build_upload_bc_argv(**params) --
    that would raise TypeError for an unexpected keyword argument."""
    task = tasks.launch("upload_bc", {"notify": True, "dry_run": True}, "operator1")
    _wait_until_finished(task.id)
    assert task.status == "ok"


# --------------------------------------------------------------------------------------
# notify flag plumbing: webapp/workflow_engine.py
# --------------------------------------------------------------------------------------


def test_start_workflow_with_notify_sends_notification_on_finish(isolated_state, fake_subprocess, monkeypatch):
    calls = []
    monkeypatch.setattr(
        notifications,
        "notify_workflow_finished",
        lambda **kwargs: calls.append(kwargs),
    )

    workflow = workflows.create_workflow(
        "Flujo de prueba",
        [{"id": "s1", "label": "Subir BC", "action": "upload_bc", "params": {}, "depends_on": []}],
    )
    run = workflow_engine.start_workflow(workflow["id"], "admin", notify=True)
    assert run.notify is True

    _wait_until_run_finished(run.id)
    assert run.status == "ok"
    _wait_until(lambda: len(calls) == 1)
    assert len(calls) == 1
    assert calls[0]["workflow_name"] == "Flujo de prueba"
    assert calls[0]["status"] == "ok"


def test_start_workflow_without_notify_never_sends_notification(isolated_state, fake_subprocess, monkeypatch):
    calls = []
    monkeypatch.setattr(
        notifications,
        "notify_workflow_finished",
        lambda **kwargs: calls.append(kwargs),
    )

    workflow = workflows.create_workflow(
        "Flujo sin aviso",
        [{"id": "s1", "label": "Subir BC", "action": "upload_bc", "params": {}, "depends_on": []}],
    )
    run = workflow_engine.start_workflow(workflow["id"], "admin")
    assert run.notify is False

    _wait_until_run_finished(run.id)
    assert calls == []
