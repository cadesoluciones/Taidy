# -*- coding: utf-8 -*-
"""
src/sync_engine/cache.py -- persisted per-mapping-side cache backing the
comparator's incremental fetch. `is_stale()` is the most important piece to
pin down: it's what decides "trust the cache" vs "force a full refresh",
and getting it wrong either defeats the whole optimization (always stale)
or silently hides deletions forever (never stale).
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.sync_engine import cache as cache_module  # noqa: E402
from src.sync_engine.cache import MappingSideCache, fields_signature, is_stale, now_iso  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_module, "_DEFAULT_DIR", tmp_path)
    monkeypatch.delenv("TAIDY_STATE_DIR", raising=False)


def test_load_side_cache_returns_none_when_missing():
    assert cache_module.load_side_cache("mapeo prueba", "source") is None


def test_save_and_load_round_trip():
    cache = MappingSideCache(
        mapping_name="mapeo prueba",
        role="source",
        system="business_central",
        watermark_value="2026-08-17T22:45:05.51Z",
        rows_by_key={"a@x.com": {"email": "a@x.com", "name": "Ana"}},
        needed_fields_signature="email,name",
        last_full_refresh_at=now_iso(),
    )
    cache_module.save_side_cache(cache)

    loaded = cache_module.load_side_cache("mapeo prueba", "source")

    assert loaded is not None
    assert loaded.watermark_value == "2026-08-17T22:45:05.51Z"
    assert loaded.rows_by_key == {"a@x.com": {"email": "a@x.com", "name": "Ana"}}
    assert loaded.needed_fields_signature == "email,name"


def test_save_side_cache_sanitizes_mapping_name_with_spaces_into_the_filename():
    cache = MappingSideCache(mapping_name="mapeo prueba", role="target", system="hubspot")
    cache_module.save_side_cache(cache)

    path = cache_module._cache_path("mapeo prueba", "target")
    assert path.is_file()
    assert " " not in path.name


def test_load_side_cache_returns_none_on_corrupt_json(tmp_path):
    path = cache_module._cache_path("mapeo prueba", "source")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not valid json", encoding="utf-8")

    assert cache_module.load_side_cache("mapeo prueba", "source") is None


def test_different_mappings_and_roles_get_separate_files():
    cache_a = MappingSideCache(mapping_name="mapeo a", role="source", system="business_central")
    cache_b = MappingSideCache(mapping_name="mapeo b", role="source", system="business_central")
    cache_module.save_side_cache(cache_a)
    cache_module.save_side_cache(cache_b)

    assert cache_module._cache_path("mapeo a", "source") != cache_module._cache_path("mapeo b", "source")
    assert cache_module._cache_path("mapeo a", "source") != cache_module._cache_path("mapeo a", "target")


def test_fields_signature_is_order_independent():
    assert fields_signature(["b", "a", "c"]) == fields_signature(["c", "b", "a"])


def test_fields_signature_differs_when_fields_differ():
    assert fields_signature(["a", "b"]) != fields_signature(["a", "b", "c"])


def test_is_stale_true_when_no_cache():
    assert is_stale(None, "email,name") is True


def test_is_stale_true_when_fields_signature_changed():
    cache = MappingSideCache(
        mapping_name="m",
        role="source",
        system="business_central",
        needed_fields_signature="email,name",
        last_full_refresh_at=now_iso(),
    )
    assert is_stale(cache, "email,name,phone") is True


def test_is_stale_true_when_never_fully_refreshed():
    cache = MappingSideCache(
        mapping_name="m", role="source", system="business_central", needed_fields_signature="email"
    )
    assert is_stale(cache, "email") is True


def test_is_stale_false_when_recent_and_fields_match():
    cache = MappingSideCache(
        mapping_name="m",
        role="source",
        system="business_central",
        needed_fields_signature="email",
        last_full_refresh_at=now_iso(),
    )
    assert is_stale(cache, "email") is False


def test_is_stale_true_when_last_full_refresh_older_than_max_age():
    old = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    cache = MappingSideCache(
        mapping_name="m", role="source", system="business_central", needed_fields_signature="email", last_full_refresh_at=old
    )
    assert is_stale(cache, "email", max_age_hours=24) is True


def test_is_stale_false_when_within_max_age():
    recent = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    cache = MappingSideCache(
        mapping_name="m", role="source", system="business_central", needed_fields_signature="email", last_full_refresh_at=recent
    )
    assert is_stale(cache, "email", max_age_hours=24) is False
