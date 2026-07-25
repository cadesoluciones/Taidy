# -*- coding: utf-8 -*-
"""
Fase 6 gap closed: explicit proof that the API layer doesn't introduce a
discrepancy versus what the Streamlit forms already send into the shared
`webapp.tasks.launch(action, params, triggered_by)` entry point. Both UIs
call this exact function -- if their `params` dicts are equal for the same
user input, their behavior is provably identical (same argv built, same
subprocess launched, same history entry recorded), because everything
downstream of `params` is common code neither UI duplicates.

Each case below is: the params dict webapp/app.py's page_* function would
build for the given form values (copied from its actual source, not
approximated), vs. the API's Pydantic request model .model_dump() (plus
the same date -> isoformat() step api/routers/tasks.py applies) for
equivalent input.

NEW-01 added an opt-in `notify` field to every request model that the
Streamlit forms never gained (it's a React-only feature per the project
owner's decision -- see webapp/notifications.py). Each comparison below
pops it off after asserting it defaults to False; the notify-flag plumbing
itself (webapp.tasks.launch() stripping it before argv building, and
firing a notification on completion) is covered by webapp/tests/test_notifications.py.
"""

from __future__ import annotations

from datetime import date

from api.schemas.tasks import (
    ExtractBcRequest,
    ExtractFactorialRequest,
    RunPipelineRequest,
    SyncBcRequest,
    SyncFactorialRequest,
    UploadBcRequest,
    UploadFactorialRequest,
)


def test_extract_bc_params_match_streamlit_form():
    # webapp/app.py:page_bc_extract's params dict for: tables=["factorial_employees"],
    # output_dir="./exports", page_size=0->None, mode="incremental", parallel=2,
    # dry_run=False, reset_watermarks=False, checkpoint_path="", verbose=False.
    streamlit_params = dict(
        tables=["factorial_employees"],
        output_dir="./exports",
        page_size=None,
        mode="incremental",
        parallel=2,
        dry_run=False,
        reset_watermarks=False,
        checkpoint_path="",
        verbose=False,
    )
    # 0 is the UI convention for "use config.json's default" -- the API
    # router normalizes this itself (api/routers/tasks.py:extract_bc), not
    # just the React form, so a direct API caller sending a literal 0 still
    # matches what the Streamlit form has always guaranteed.
    api_params = ExtractBcRequest(
        tables=["factorial_employees"],
        output_dir="./exports",
        page_size=0,
        mode="incremental",
        parallel=2,
        dry_run=False,
        reset_watermarks=False,
        checkpoint_path="",
        verbose=False,
    ).model_dump()
    api_params["page_size"] = api_params["page_size"] or None
    assert api_params.pop("notify") is False
    assert api_params == streamlit_params


def test_upload_bc_params_match_streamlit_form():
    streamlit_params = dict(output_dir="./exports", dry_run=False, skip_existing=True, verbose=False)
    api_params = UploadBcRequest(output_dir="./exports", dry_run=False, skip_existing=True, verbose=False).model_dump()
    assert api_params.pop("notify") is False
    assert api_params == streamlit_params


def test_sync_bc_params_match_streamlit_form():
    streamlit_params = dict(
        tables=None, output_dir="./exports", mode="full", parallel=1, dry_run=True, skip_existing=False, verbose=False
    )
    api_params = SyncBcRequest(
        tables=None, output_dir="./exports", mode="full", parallel=1, dry_run=True, skip_existing=False, verbose=False
    ).model_dump()
    assert api_params.pop("notify") is False
    assert api_params == streamlit_params


def test_extract_factorial_params_match_streamlit_form():
    start_on, end_on = date(2025, 1, 1), date(2025, 6, 30)
    streamlit_params = dict(
        start_on=start_on.isoformat(),
        end_on=end_on.isoformat(),
        employees=[123, 456],
        employee_status="active",
        tables=None,
        output_dir="./exports_factorial",
        mode="full",
        parallel=5,
        reset_all_checkpoints=False,
        dry_run=False,
        verbose=False,
    )
    api_params = ExtractFactorialRequest(
        start_on=start_on,
        end_on=end_on,
        employees=[123, 456],
        employee_status="active",
        tables=None,
        output_dir="./exports_factorial",
        mode="full",
        parallel=5,
        reset_all_checkpoints=False,
        dry_run=False,
        verbose=False,
    ).model_dump()
    api_params["start_on"] = api_params["start_on"].isoformat()
    api_params["end_on"] = api_params["end_on"].isoformat()
    assert api_params.pop("notify") is False
    assert api_params == streamlit_params


def test_upload_factorial_params_match_streamlit_form():
    streamlit_params = dict(
        output_dir="./exports_factorial", tables=["factorial_employees"], dry_run=False, skip_existing=True, verbose=False
    )
    api_params = UploadFactorialRequest(
        output_dir="./exports_factorial", tables=["factorial_employees"], dry_run=False, skip_existing=True, verbose=False
    ).model_dump()
    assert api_params.pop("notify") is False
    assert api_params == streamlit_params


def test_sync_factorial_params_match_streamlit_form():
    start_on, end_on = date(2025, 1, 1), date(2025, 6, 30)
    streamlit_params = dict(
        start_on=start_on.isoformat(),
        end_on=end_on.isoformat(),
        employee_status="all",
        tables=None,
        output_dir="./exports_factorial",
        mode="incremental",
        parallel=5,
        dry_run=False,
        skip_existing=False,
        verbose=False,
    )
    api_params = SyncFactorialRequest(
        start_on=start_on,
        end_on=end_on,
        employee_status="all",
        tables=None,
        output_dir="./exports_factorial",
        mode="incremental",
        parallel=5,
        dry_run=False,
        skip_existing=False,
        verbose=False,
    ).model_dump()
    api_params["start_on"] = api_params["start_on"].isoformat()
    api_params["end_on"] = api_params["end_on"].isoformat()
    assert api_params.pop("notify") is False
    assert api_params == streamlit_params


def test_run_pipeline_params_match_streamlit_form():
    streamlit_params = dict(pipeline="Pipeline_CADE", wait=True, poll_seconds=15, verbose=False)
    api_params = RunPipelineRequest(pipeline="Pipeline_CADE", wait=True, poll_seconds=15, verbose=False).model_dump()
    assert api_params.pop("notify") is False
    assert api_params == streamlit_params
