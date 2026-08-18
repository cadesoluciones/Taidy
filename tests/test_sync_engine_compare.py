# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest

from src.sync_engine import cache as cache_module
from src.sync_engine import compare as compare_module
from webapp import sync_mappings


@pytest.fixture(autouse=True)
def _isolated_sync_cache(tmp_path, monkeypatch):
    # Every test gets a fresh, empty cache dir -- without this, compare_mapping's
    # incremental fetch cache (src/sync_engine/cache.py) would persist real
    # files between test runs and between tests in the same run (several tests
    # below reuse the same mapping name), causing a "warm" cache to route a
    # later test through the incremental delta-fetch path instead of the
    # plain `fetch_rows` these tests monkeypatch.
    monkeypatch.setattr(cache_module, "_DEFAULT_DIR", tmp_path / "sync_cache")


@pytest.fixture
def isolated_mappings(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_mappings, "_SYNC_MAPPINGS_PATH", tmp_path / "sync_mappings.yaml")
    sync_mappings.add_mapping(
        "bc_contact_a_hubspot_contacts",
        {"system": "business_central", "table": "bc_contact"},
        {"system": "hubspot", "table": "hubspot_contacts"},
        {"source": "email", "target": "email"},
        {"source": "systemModifiedAt", "target": "lastmodifieddate"},
        [
            {"source": "email", "target": "email"},
            {"source": "name", "target": "firstname"},
        ],
    )
    return "bc_contact_a_hubspot_contacts"


@pytest.fixture
def isolated_mapping_with_source_filter(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_mappings, "_SYNC_MAPPINGS_PATH", tmp_path / "sync_mappings.yaml")
    sync_mappings.add_mapping(
        "bc_persons_a_hubspot_contacts",
        {"system": "business_central", "table": "bc_contact"},
        {"system": "hubspot", "table": "hubspot_contacts"},
        {"source": "email", "target": "email"},
        {"source": "systemModifiedAt", "target": "lastmodifieddate"},
        [
            {"source": "email", "target": "email"},
            {"source": "name", "target": "firstname"},
        ],
        source_filter={"field": "type", "equals": "Person"},
    )
    return "bc_persons_a_hubspot_contacts"


def _fake_fetch_rows(source_rows, target_rows):
    def _fetch(system, table_name, needed_fields):
        return source_rows if system == "business_central" else target_rows

    return _fetch


def test_compare_classifies_new_record_in_each_direction(isolated_mappings, monkeypatch):
    source_rows = [{"email": "only-in-bc@example.com", "name": "Ana", "systemModifiedAt": "2026-01-01T00:00:00Z"}]
    target_rows = [{"email": "only-in-hubspot@example.com", "firstname": "Luis", "lastmodifieddate": "2026-01-01T00:00:00Z"}]
    monkeypatch.setattr(compare_module, "fetch_rows", _fake_fetch_rows(source_rows, target_rows))

    report = compare_module.compare_mapping(isolated_mappings)

    assert [a.key for a in report.create_in_target] == ["only-in-bc@example.com"]
    assert [a.key for a in report.create_in_source] == ["only-in-hubspot@example.com"]
    assert report.update_target == []
    assert report.update_source == []
    assert report.unchanged == []
    assert report.skipped == []


def test_compare_picks_the_more_recent_side_as_winner(isolated_mappings, monkeypatch):
    source_rows = [{"email": "a@example.com", "name": "Ana", "systemModifiedAt": "2026-03-01T00:00:00Z"}]
    target_rows = [{"email": "a@example.com", "firstname": "Ana Vieja", "lastmodifieddate": "2026-01-01T00:00:00Z"}]
    monkeypatch.setattr(compare_module, "fetch_rows", _fake_fetch_rows(source_rows, target_rows))

    report = compare_module.compare_mapping(isolated_mappings)

    assert [a.key for a in report.update_target] == ["a@example.com"]
    assert report.update_source == []
    assert report.create_in_target == []
    assert report.create_in_source == []


def test_compare_treats_identical_dates_as_unchanged(isolated_mappings, monkeypatch):
    same = "2026-03-01T00:00:00Z"
    source_rows = [{"email": "a@example.com", "name": "Ana", "systemModifiedAt": same}]
    target_rows = [{"email": "a@example.com", "firstname": "Ana", "lastmodifieddate": same}]
    monkeypatch.setattr(compare_module, "fetch_rows", _fake_fetch_rows(source_rows, target_rows))

    report = compare_module.compare_mapping(isolated_mappings)

    assert [a.key for a in report.unchanged] == ["a@example.com"]
    assert report.update_target == []
    assert report.update_source == []


def test_compare_missing_date_on_one_side_lets_the_other_win(isolated_mappings, monkeypatch):
    source_rows = [{"email": "a@example.com", "name": "Ana", "systemModifiedAt": ""}]
    target_rows = [{"email": "a@example.com", "firstname": "Ana", "lastmodifieddate": "2026-01-01T00:00:00Z"}]
    monkeypatch.setattr(compare_module, "fetch_rows", _fake_fetch_rows(source_rows, target_rows))

    report = compare_module.compare_mapping(isolated_mappings)

    # Target has a track record, source doesn't -- target wins -> source gets updated.
    assert [a.key for a in report.update_source] == ["a@example.com"]
    assert report.update_target == []


def test_compare_skips_empty_and_duplicate_keys(isolated_mappings, monkeypatch):
    source_rows = [
        {"email": "", "name": "Sin email", "systemModifiedAt": "2026-01-01T00:00:00Z"},
        {"email": "dup@example.com", "name": "Uno", "systemModifiedAt": "2026-01-01T00:00:00Z"},
        {"email": "dup@example.com", "name": "Dos", "systemModifiedAt": "2026-01-02T00:00:00Z"},
    ]
    target_rows = []
    monkeypatch.setattr(compare_module, "fetch_rows", _fake_fetch_rows(source_rows, target_rows))

    report = compare_module.compare_mapping(isolated_mappings)

    reasons = {(s.system, s.reason) for s in report.skipped}
    assert ("source", "empty_key") in reasons
    assert ("source", "duplicate_key") in reasons
    assert report.create_in_target == []


def test_compare_unknown_mapping_raises(isolated_mappings):
    with pytest.raises(compare_module.SyncCompareError):
        compare_module.compare_mapping("does-not-exist")


def test_parse_date_handles_z_suffix_and_invalid_input():
    assert compare_module._parse_date("2026-01-01T00:00:00Z") is not None
    assert compare_module._parse_date("") is None
    assert compare_module._parse_date(None) is None
    assert compare_module._parse_date("not-a-date") is None


# --------------------------------------------------------------------------------------
# Incremental fetch cache (src/sync_engine/cache.py)
# --------------------------------------------------------------------------------------


def test_compare_second_call_uses_incremental_delta_not_full_fetch(isolated_mappings, monkeypatch):
    calls = {"full": 0, "since": []}

    def fake_fetch_rows(system, table_name, needed_fields):
        calls["full"] += 1
        if system == "business_central":
            return [{"email": "a@example.com", "name": "Ana", "systemModifiedAt": "2026-01-01T00:00:00Z"}]
        return [{"email": "a@example.com", "firstname": "Ana", "lastmodifieddate": "2026-02-01T00:00:00Z"}]

    def fake_fetch_since(system, table_name, needed_fields, date_field, since):
        calls["since"].append((system, since))
        return []

    monkeypatch.setattr(compare_module, "fetch_rows", fake_fetch_rows)
    monkeypatch.setattr(compare_module, "_fetch_since", fake_fetch_since)

    compare_module.compare_mapping(isolated_mappings)  # no cache yet -> full fetch both sides
    assert calls["full"] == 2

    compare_module.compare_mapping(isolated_mappings)  # cache warm -> incremental both sides
    assert ("business_central", "2026-01-01T00:00:00Z") in calls["since"]
    assert ("hubspot", "2026-02-01T00:00:00Z") in calls["since"]
    assert calls["full"] == 2  # unchanged -- second call never did a full fetch


def test_compare_incremental_merges_delta_over_previously_cached_rows(isolated_mappings, monkeypatch):
    full_rows = [
        {"email": "a@example.com", "name": "Ana", "systemModifiedAt": "2026-01-01T00:00:00Z"},
        {"email": "b@example.com", "name": "Beto", "systemModifiedAt": "2026-01-01T00:00:00Z"},
    ]
    monkeypatch.setattr(compare_module, "fetch_rows", _fake_fetch_rows(full_rows, []))

    report1 = compare_module.compare_mapping(isolated_mappings)
    assert {a.key for a in report1.create_in_target} == {"a@example.com", "b@example.com"}

    # Only "a" comes back in the delta; "b" must still show up, recovered
    # from the cache, without ever being re-fetched.
    def fake_fetch_since(system, table_name, needed_fields, date_field, since):
        if system == "business_central":
            return [{"email": "a@example.com", "name": "Ana Actualizada", "systemModifiedAt": "2026-02-01T00:00:00Z"}]
        return []

    monkeypatch.setattr(compare_module, "_fetch_since", fake_fetch_since)
    report2 = compare_module.compare_mapping(isolated_mappings)

    assert {a.key for a in report2.create_in_target} == {"a@example.com", "b@example.com"}
    updated = next(a.source_row for a in report2.create_in_target if a.key == "a@example.com")
    assert updated["name"] == "Ana Actualizada"


def test_compare_force_full_ignores_a_warm_cache(isolated_mappings, monkeypatch):
    calls = {"full": 0, "since": 0}

    def fake_fetch_rows(system, table_name, needed_fields):
        calls["full"] += 1
        return []

    def fake_fetch_since(*args, **kwargs):
        calls["since"] += 1
        return []

    monkeypatch.setattr(compare_module, "fetch_rows", fake_fetch_rows)
    monkeypatch.setattr(compare_module, "_fetch_since", fake_fetch_since)

    compare_module.compare_mapping(isolated_mappings)  # warms the cache
    assert calls["full"] == 2

    compare_module.compare_mapping(isolated_mappings, force_full=True)
    assert calls["full"] == 4  # both sides did a full fetch again
    assert calls["since"] == 0


def test_compare_forces_full_refresh_when_cache_is_older_than_max_age(isolated_mappings, monkeypatch):
    calls = {"full": 0, "since": 0}

    def fake_fetch_rows(system, table_name, needed_fields):
        calls["full"] += 1
        return []

    def fake_fetch_since(*args, **kwargs):
        calls["since"] += 1
        return []

    monkeypatch.setattr(compare_module, "fetch_rows", fake_fetch_rows)
    monkeypatch.setattr(compare_module, "_fetch_since", fake_fetch_since)

    compare_module.compare_mapping(isolated_mappings)
    assert calls["full"] == 2

    from datetime import datetime, timedelta, timezone

    for role in ("source", "target"):
        cache = cache_module.load_side_cache(isolated_mappings, role)
        cache.last_full_refresh_at = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        cache_module.save_side_cache(cache)

    compare_module.compare_mapping(isolated_mappings)
    assert calls["full"] == 4
    assert calls["since"] == 0


def test_compare_keeps_flagging_empty_and_duplicate_keys_after_a_warm_cache_refresh(isolated_mappings, monkeypatch):
    # Regression: the cache's rows_by_key is a dict, which can't represent an
    # empty key (collides with every other empty key) or a duplicated key
    # (would silently collapse to "last one wins"). If the incremental
    # fetcher built its cache the same way it builds the returned row list,
    # a record skipped as empty/duplicate_key on the first (full) compare
    # would silently stop being skipped -- or worse, get counted as a
    # legitimate create/update -- on the very next (cached) compare, even
    # though nothing about the real data changed. This was caught live
    # against a real BC/HubSpot mapping: create_in_target jumped from 574 to
    # 872 and skipped dropped from 2213 to 0 between two back-to-back calls.
    source_rows = [
        {"email": "", "name": "Sin email", "systemModifiedAt": "2026-01-01T00:00:00Z"},
        {"email": "dup@example.com", "name": "Uno", "systemModifiedAt": "2026-01-01T00:00:00Z"},
        {"email": "dup@example.com", "name": "Dos", "systemModifiedAt": "2026-01-02T00:00:00Z"},
        {"email": "ok@example.com", "name": "Ana", "systemModifiedAt": "2026-01-01T00:00:00Z"},
    ]
    monkeypatch.setattr(compare_module, "fetch_rows", _fake_fetch_rows(source_rows, []))

    report1 = compare_module.compare_mapping(isolated_mappings)
    reasons1 = {(s.system, s.reason) for s in report1.skipped}
    assert ("source", "empty_key") in reasons1
    assert ("source", "duplicate_key") in reasons1
    assert [a.key for a in report1.create_in_target] == ["ok@example.com"]

    # Second call: cache is warm, no real change since the watermark, so this
    # goes through the incremental path -- the empty/duplicate rows must
    # still be reported exactly as before, not silently promoted.
    def fake_fetch_since(system, table_name, needed_fields, date_field, since):
        return []

    monkeypatch.setattr(compare_module, "_fetch_since", fake_fetch_since)
    report2 = compare_module.compare_mapping(isolated_mappings)

    reasons2 = {(s.system, s.reason) for s in report2.skipped}
    assert ("source", "empty_key") in reasons2
    assert ("source", "duplicate_key") in reasons2
    assert [a.key for a in report2.create_in_target] == ["ok@example.com"]


# --------------------------------------------------------------------------------------
# Row filter (source_filter/target_filter) -- lets a mapping opt into only a
# subset of a shared table, e.g. BC's bc_contact holding both Person and
# Company records but only Person belonging in HubSpot's "contacts" object.
# --------------------------------------------------------------------------------------


def test_compare_source_filter_excludes_non_matching_rows_entirely(isolated_mapping_with_source_filter, monkeypatch):
    source_rows = [
        {"email": "person@example.com", "name": "Ana", "type": "Person", "systemModifiedAt": "2026-01-01T00:00:00Z"},
        {"email": "company@example.com", "name": "ACME", "type": "Company", "systemModifiedAt": "2026-01-01T00:00:00Z"},
    ]
    monkeypatch.setattr(compare_module, "fetch_rows", _fake_fetch_rows(source_rows, []))

    report = compare_module.compare_mapping(isolated_mapping_with_source_filter)

    # The Company row is filtered out before it ever reaches key indexing --
    # not reported as create_in_target, and not reported as skipped either.
    assert [a.key for a in report.create_in_target] == ["person@example.com"]
    assert report.skipped == []


def test_compare_source_filter_field_is_requested_from_hubspot_when_filter_is_on_target(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_mappings, "_SYNC_MAPPINGS_PATH", tmp_path / "sync_mappings.yaml")
    sync_mappings.add_mapping(
        "hubspot_contacts_to_bc",
        {"system": "hubspot", "table": "hubspot_contacts"},
        {"system": "business_central", "table": "bc_contact"},
        {"source": "email", "target": "email"},
        {"source": "lastmodifieddate", "target": "systemModifiedAt"},
        [{"source": "email", "target": "email"}],
        source_filter={"field": "lifecyclestage", "equals": "customer"},
    )

    captured_needed_fields = {}

    def fake_fetch_rows(system, table_name, needed_fields):
        captured_needed_fields[system] = set(needed_fields)
        return []

    monkeypatch.setattr(compare_module, "fetch_rows", fake_fetch_rows)
    compare_module.compare_mapping("hubspot_contacts_to_bc")

    # Even though "lifecyclestage" isn't in matching_key/date_field/fields,
    # it must still be requested -- HubSpot only returns properties it's
    # explicitly asked for, unlike BC which returns everything regardless.
    assert "lifecyclestage" in captured_needed_fields["hubspot"]


def test_compare_row_that_changes_out_of_the_filter_is_evicted_on_incremental_refresh(
    isolated_mapping_with_source_filter, monkeypatch
):
    full_rows = [
        {"email": "person@example.com", "name": "Ana", "type": "Person", "systemModifiedAt": "2026-01-01T00:00:00Z"},
    ]
    monkeypatch.setattr(compare_module, "fetch_rows", _fake_fetch_rows(full_rows, []))

    report1 = compare_module.compare_mapping(isolated_mapping_with_source_filter)
    assert [a.key for a in report1.create_in_target] == ["person@example.com"]

    # The same record got reclassified to Company and touched since the
    # watermark -- the delta fetch sees it, but the filter now excludes it.
    def fake_fetch_since(system, table_name, needed_fields, date_field, since):
        return [
            {
                "email": "person@example.com",
                "name": "Ana",
                "type": "Company",
                "systemModifiedAt": "2026-02-01T00:00:00Z",
            }
        ]

    monkeypatch.setattr(compare_module, "_fetch_since", fake_fetch_since)
    report2 = compare_module.compare_mapping(isolated_mapping_with_source_filter)

    # Must disappear from this mapping's view entirely -- not linger as a
    # stale cached "still valid" row just because the delta excluded it.
    assert report2.create_in_target == []


def test_bc_reader_rejects_unknown_table(tmp_path, monkeypatch):
    # No BC_CLIENT_SECRET / real config wiring needed to hit this branch --
    # the table lookup fails before any network call would happen.
    monkeypatch.setenv("BC_CLIENT_SECRET", "fake")
    monkeypatch.setattr(
        "src.bc_client.config.load_settings",
        lambda: type("S", (), {"tables": []})(),
    )
    with pytest.raises(compare_module.SyncCompareError):
        compare_module._fetch_bc_rows("does_not_exist")
