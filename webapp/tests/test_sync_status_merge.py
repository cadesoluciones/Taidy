# -*- coding: utf-8 -*-
"""
Regression test for a real UI bug: a sync task (extract + upload in one run)
used to show TWO cards per table -- one for the extract phase, one for the
upload phase (webapp/tasks.py concatenated extract_statuses + upload_statuses).
merge_sync_statuses() instead folds the upload outcome into the extract
entry, so the UI shows one card per table with a second icon for the upload
result.
"""

from __future__ import annotations

from webapp.adapter import TableStatus, merge_sync_statuses


def test_extracted_and_uploaded_merges_into_one_entry():
    extract = [TableStatus(name="customers", status="ok", detail="120 filas")]
    upload = [TableStatus(name="customers.csv", status="ok", detail="subido")]

    merged = merge_sync_statuses(extract, upload)

    assert len(merged) == 1
    entry = merged[0]
    assert entry.name == "customers"
    assert entry.status == "ok"
    assert entry.detail == "120 filas"
    assert entry.upload_status == "ok"
    assert entry.upload_detail == "subido"


def test_extracted_but_not_yet_uploaded_is_pending():
    extract = [TableStatus(name="customers", status="ok", detail="120 filas")]
    upload: list[TableStatus] = []  # upload phase hasn't reached this table yet

    merged = merge_sync_statuses(extract, upload)

    assert len(merged) == 1
    assert merged[0].upload_status == "pending"
    assert merged[0].upload_detail == "pendiente de subir"


def test_upload_failure_is_reflected_on_the_same_entry():
    extract = [TableStatus(name="customers", status="ok", detail="120 filas")]
    upload = [TableStatus(name="customers.csv", status="error", detail="fallo al subir")]

    merged = merge_sync_statuses(extract, upload)

    assert merged[0].status == "ok"  # extract itself succeeded
    assert merged[0].upload_status == "error"
    assert merged[0].upload_detail == "fallo al subir"


def test_extract_failure_has_no_upload_status():
    extract = [TableStatus(name="customers", status="error", detail="empezó pero no se confirmó su finalización")]
    upload: list[TableStatus] = []

    merged = merge_sync_statuses(extract, upload)

    assert len(merged) == 1
    assert merged[0].status == "error"
    assert merged[0].upload_status is None
    assert merged[0].upload_detail == ""


def test_never_produces_two_entries_for_the_same_table():
    extract = [
        TableStatus(name="customers", status="ok", detail="120 filas"),
        TableStatus(name="invoices", status="ok", detail="50 filas"),
    ]
    upload = [
        TableStatus(name="customers.csv", status="ok", detail="subido"),
        TableStatus(name="invoices.csv", status="ok", detail="subido"),
    ]

    merged = merge_sync_statuses(extract, upload)

    assert len(merged) == 2  # not 4 (2 extract + 2 upload, the old behavior)
    assert {e.name for e in merged} == {"customers", "invoices"}


def test_upload_skipped_because_it_already_existed_is_reflected():
    extract = [TableStatus(name="customers", status="ok", detail="120 filas")]
    upload = [TableStatus(name="customers.csv", status="skipped", detail="ya existía en OneLake")]

    merged = merge_sync_statuses(extract, upload)

    assert merged[0].upload_status == "skipped"
    assert merged[0].upload_detail == "ya existía en OneLake"
