# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest

from src.sync_engine import compare as compare_module
from webapp import sync_mappings


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
