# -*- coding: utf-8 -*-
"""
Sessions used to live only in an in-memory dict, so restarting the API
process silently logged out everyone -- session_store.py persists them to a
JSON file instead. These tests prove a session survives even when nothing
is cached in memory (every call reads the file fresh, see the module
docstring), which is the actual property that matters: a real process
restart clears any Python-level cache but never touches the file on disk.
"""

from __future__ import annotations

from api import session_store


def test_session_survives_with_no_in_memory_state(isolated_state):
    session_id = session_store.create_session("alice")

    assert session_store._read() == {session_id: "alice"}
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
