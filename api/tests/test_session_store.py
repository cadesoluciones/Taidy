# -*- coding: utf-8 -*-
"""
Sessions used to live only in an in-memory dict, so restarting the API
process silently logged out everyone -- session_store.py persists them to a
JSON file instead. These tests prove a session survives even when nothing
is cached in memory (every call reads the file fresh, see the module
docstring), which is the actual property that matters: a real process
restart clears any Python-level cache but never touches the file on disk.

Also covers "sesiones activas": listing/revoking a user's sessions by a
non-reversible reference (never the real session_id -- that value IS the
bearer credential), and reading a pre-upgrade sessions.json where each
value was still a plain username string.
"""

from __future__ import annotations

import json

from api import session_store


def test_session_survives_with_no_in_memory_state(isolated_state):
    session_id = session_store.create_session("alice")

    stored = session_store._read()
    assert set(stored.keys()) == {session_id}
    assert stored[session_id]["username"] == "alice"
    assert session_store.get_session_username(session_id) == "alice"


def test_destroy_session_removes_it_from_disk(isolated_state):
    session_id = session_store.create_session("alice")
    session_store.destroy_session(session_id)

    assert session_store.get_session_username(session_id) is None
    assert session_store._read() == {}


def test_get_session_username_returns_none_for_unknown_or_missing_session(isolated_state):
    assert session_store.get_session_username(None) is None
    assert session_store.get_session_username("does-not-exist") is None


def test_multiple_sessions_coexist(isolated_state):
    a = session_store.create_session("alice")
    b = session_store.create_session("bob")

    assert session_store.get_session_username(a) == "alice"
    assert session_store.get_session_username(b) == "bob"


def test_get_session_username_does_not_write_to_disk(isolated_state):
    """Deliberate: this runs on every authenticated request, so it must stay
    a pure read -- see session_store.get_session_username's docstring."""
    session_id = session_store.create_session("alice")
    before = session_store._SESSIONS_PATH.read_bytes()

    session_store.get_session_username(session_id)

    assert session_store._SESSIONS_PATH.read_bytes() == before


def test_a_pre_upgrade_plain_string_session_still_works(isolated_state):
    """sessions.json written before "sesiones activas" stored `session_id ->
    username` directly (no dict, no timestamps) -- reading it must not log
    everyone out."""
    session_store._SESSIONS_PATH.write_text(json.dumps({"old-session-id": "alice"}), encoding="utf-8")

    assert session_store.get_session_username("old-session-id") == "alice"
    sessions = session_store.list_sessions_for_user("alice")
    assert len(sessions) == 1
    assert "created_at" in sessions[0]


def test_list_sessions_for_user_never_exposes_the_real_session_id(isolated_state):
    session_id = session_store.create_session("alice")

    sessions = session_store.list_sessions_for_user("alice")

    assert len(sessions) == 1
    assert sessions[0]["session_ref"] != session_id
    assert session_id not in json.dumps(sessions)


def test_list_sessions_for_user_only_returns_that_users_sessions(isolated_state):
    session_store.create_session("alice")
    session_store.create_session("alice")
    session_store.create_session("bob")

    assert len(session_store.list_sessions_for_user("alice")) == 2
    assert len(session_store.list_sessions_for_user("bob")) == 1
    assert session_store.list_sessions_for_user("carol") == []


def test_revoke_session_by_ref_logs_that_session_out(isolated_state):
    session_id = session_store.create_session("alice")
    session_ref = session_store.list_sessions_for_user("alice")[0]["session_ref"]

    revoked = session_store.revoke_session_by_ref("alice", session_ref)

    assert revoked is True
    assert session_store.get_session_username(session_id) is None


def test_revoke_session_by_ref_scoped_to_the_given_username(isolated_state):
    session_store.create_session("alice")
    alice_ref = session_store.list_sessions_for_user("alice")[0]["session_ref"]

    # Someone else's username can't revoke alice's session even with the
    # right ref -- prevents any cross-user reach-through via a guessed ref.
    revoked = session_store.revoke_session_by_ref("bob", alice_ref)

    assert revoked is False
    assert len(session_store.list_sessions_for_user("alice")) == 1


def test_revoke_unknown_ref_returns_false(isolated_state):
    assert session_store.revoke_session_by_ref("alice", "0" * 12) is False
