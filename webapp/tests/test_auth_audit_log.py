# -*- coding: utf-8 -*-
"""
webapp/auth.py's audit log (login/logout/password-change/authorization
events) was append-only with no size cap -- it grew forever, and every read
(api/routers/audit.py's GET /audit) loaded the entire file into memory no
matter how big it got. This covers the rotation added to bound its on-disk
size (audit.log -> .1, .2, ... instead of growing forever, discarding only
the oldest backup once the cap is exceeded) and confirms get_audit_log()
still returns correct, newest-first results across a rotation boundary.
"""

from __future__ import annotations

import json

from webapp import auth


def _line(event: str, user: str) -> str:
    return json.dumps({"ts": "2026-01-01T00:00:00+00:00", "event": event, "outcome": "ok", "user": user, "detail": ""})


def _backup_path(n: int):
    return auth._AUDIT_LOG_PATH.parent / f"{auth._AUDIT_LOG_PATH.name}.{n}"


def test_audit_appends_json_lines_newest_first(isolated_state):
    auth._audit("login", "ok", user="alice", detail="")
    auth._audit("logout", "ok", user="alice", detail="")

    entries = auth.get_audit_log()

    assert [e["event"] for e in entries] == ["logout", "login"]


def test_get_audit_log_respects_limit(isolated_state):
    for i in range(5):
        auth._audit("login", "ok", user=f"user{i}", detail="")

    entries = auth.get_audit_log(limit=2)

    assert [e["user"] for e in entries] == ["user4", "user3"]


def test_rotate_is_a_no_op_when_no_file_exists(isolated_state):
    auth._rotate_audit_log_if_needed()  # must not raise
    assert not auth._AUDIT_LOG_PATH.exists()


def test_rotate_is_a_no_op_below_the_size_threshold(isolated_state, monkeypatch):
    monkeypatch.setattr(auth, "_MAX_AUDIT_LOG_BYTES", 10_000)
    auth._AUDIT_LOG_PATH.write_text("small\n", encoding="utf-8")

    auth._rotate_audit_log_if_needed()

    assert auth._AUDIT_LOG_PATH.read_text(encoding="utf-8") == "small\n"
    assert not _backup_path(1).exists()


def test_rotate_shifts_existing_backups_and_starts_fresh(isolated_state, monkeypatch):
    monkeypatch.setattr(auth, "_MAX_AUDIT_BACKUPS", 3)
    monkeypatch.setattr(auth, "_MAX_AUDIT_LOG_BYTES", 1)  # force rotation regardless of actual size
    auth._AUDIT_LOG_PATH.write_text("live\n", encoding="utf-8")
    _backup_path(1).write_text("backup1\n", encoding="utf-8")
    _backup_path(2).write_text("backup2\n", encoding="utf-8")

    auth._rotate_audit_log_if_needed()

    assert not auth._AUDIT_LOG_PATH.exists()
    assert _backup_path(1).read_text(encoding="utf-8") == "live\n"
    assert _backup_path(2).read_text(encoding="utf-8") == "backup1\n"
    assert _backup_path(3).read_text(encoding="utf-8") == "backup2\n"


def test_rotate_drops_the_oldest_backup_beyond_the_cap(isolated_state, monkeypatch):
    monkeypatch.setattr(auth, "_MAX_AUDIT_BACKUPS", 2)
    monkeypatch.setattr(auth, "_MAX_AUDIT_LOG_BYTES", 1)
    auth._AUDIT_LOG_PATH.write_text("live\n", encoding="utf-8")
    _backup_path(1).write_text("backup1\n", encoding="utf-8")
    _backup_path(2).write_text("backup2-oldest\n", encoding="utf-8")

    auth._rotate_audit_log_if_needed()

    assert _backup_path(1).read_text(encoding="utf-8") == "live\n"
    assert _backup_path(2).read_text(encoding="utf-8") == "backup1\n"
    assert not _backup_path(3).exists()  # "backup2-oldest" is dropped, not kept as .3


def test_audit_rotates_automatically_once_the_live_file_grows_past_the_cap(isolated_state, monkeypatch):
    monkeypatch.setattr(auth, "_MAX_AUDIT_LOG_BYTES", 1)
    monkeypatch.setattr(auth, "_MAX_AUDIT_BACKUPS", 2)

    auth._audit("login", "ok", user="first", detail="")  # file now > 1 byte
    auth._audit("login", "ok", user="second", detail="")  # must rotate before appending

    assert _backup_path(1).exists()
    live_entries = [json.loads(line) for line in auth._AUDIT_LOG_PATH.read_text(encoding="utf-8").splitlines()]
    assert [e["user"] for e in live_entries] == ["second"]


def test_get_audit_log_falls_back_to_backup_when_live_file_is_short(isolated_state):
    _backup_path(1).write_text(_line("login", "old1") + "\n" + _line("login", "old2") + "\n", encoding="utf-8")
    auth._AUDIT_LOG_PATH.write_text(_line("login", "new1") + "\n", encoding="utf-8")

    entries = auth.get_audit_log(limit=3)

    assert [e["user"] for e in entries] == ["new1", "old2", "old1"]


def test_get_audit_log_never_returns_more_than_the_live_file_when_it_already_satisfies_limit(isolated_state):
    _backup_path(1).write_text(_line("login", "should_not_appear") + "\n", encoding="utf-8")
    auth._AUDIT_LOG_PATH.write_text(_line("login", "a") + "\n" + _line("login", "b") + "\n", encoding="utf-8")

    entries = auth.get_audit_log(limit=2)

    assert [e["user"] for e in entries] == ["b", "a"]
