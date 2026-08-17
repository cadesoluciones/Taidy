# -*- coding: utf-8 -*-
"""
Thin adapter between the web UI and NEXUS-BDB's existing CLI entry points.

Nothing here reimplements extraction/upload logic, and nothing here executes
anything either: every function builds an argv list from validated UI inputs,
exactly the argv the real CLIs (`python -m src.main ...`, etc.) already
accept. webapp/tasks.py is what actually launches those CLIs as subprocesses.

This module also owns the per-table/per-file status parsing: since the
backend returns only aggregate counts, tasks.py asks these functions to
reconstruct a per-table breakdown from the captured subprocess output.

Adding a new UI action later means: add an argv-builder function here (or
reuse one), and wire it into webapp/tasks.py's MODULE_FOR_ACTION if it's a
new action key — never editing src/**.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Sequence

import yaml

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.config_loader import load_config_data  # noqa: E402
from webapp import table_configs  # noqa: E402

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(text: str) -> str:
    """Rich forces ANSI color codes even on non-tty output; strip for display/parsing."""
    return _ANSI_RE.sub("", text)


@dataclass
class TableStatus:
    """Per-table/per-file outcome, reconstructed from the captured log text."""

    name: str
    status: str  # "ok" | "skipped" | "dry_run" | "error" | "unknown"
    detail: str = ""
    phase: str = ""  # only set on combined sync results: "extraer" | "subir"
    # Only set by merge_sync_statuses(): a sync task's upload-phase outcome
    # for this same table, folded into the extract entry instead of a
    # second, separate card for what a user experiences as one table.
    upload_status: Optional[str] = None
    upload_detail: str = ""


def _flag(argv: List[str], name: str, value: bool) -> None:
    if value:
        argv.append(name)


def _opt(argv: List[str], name: str, value) -> None:
    if value not in (None, ""):
        argv.extend([name, str(value)])


def _opt_list(argv: List[str], name: str, values: Optional[Sequence[str]]) -> None:
    if values:
        argv.append(name)
        argv.extend(str(v) for v in values)


# --------------------------------------------------------------------------------------
# argv builders — Business Central
# --------------------------------------------------------------------------------------


def build_extract_bc_argv(
    *,
    tables: Optional[Sequence[str]] = None,
    output_dir: str = "",
    page_size: Optional[int] = None,
    mode: str = "incremental",
    parallel: int = 1,
    dry_run: bool = False,
    reset_watermarks: bool = False,
    checkpoint_path: str = "",
    verbose: bool = False,
) -> List[str]:
    argv: List[str] = []
    _opt_list(argv, "--tables", tables)
    _opt(argv, "--output-dir", output_dir)
    _opt(argv, "--page-size", page_size)
    argv.extend(["--mode", mode])
    argv.extend(["--parallel", str(parallel)])
    _flag(argv, "--dry-run", dry_run)
    _flag(argv, "--reset-watermarks", reset_watermarks)
    _opt(argv, "--checkpoint-path", checkpoint_path)
    _flag(argv, "--verbose", verbose)
    return argv


def build_upload_bc_argv(
    *,
    output_dir: str = "./exports",
    dry_run: bool = False,
    skip_existing: bool = False,
    verbose: bool = False,
) -> List[str]:
    argv: List[str] = ["--output-dir", output_dir]
    _flag(argv, "--dry-run", dry_run)
    _flag(argv, "--skip-existing", skip_existing)
    _flag(argv, "--verbose", verbose)
    return argv


# --------------------------------------------------------------------------------------
# argv builders — Factorial HR
# --------------------------------------------------------------------------------------


def build_extract_factorial_argv(
    *,
    start_on: str,
    end_on: str,
    employees: Optional[Sequence[int]] = None,
    employee_status: str = "active",
    tables: Optional[Sequence[str]] = None,
    output_dir: str = "",
    mode: str = "full",
    parallel: int = 1,
    reset_checkpoints: Optional[Sequence[str]] = None,
    reset_all_checkpoints: bool = False,
    dry_run: bool = False,
    verbose: bool = False,
) -> List[str]:
    argv: List[str] = ["--start-on", start_on, "--end-on", end_on]
    if employees:
        argv.append("--employees")
        argv.extend(str(e) for e in employees)
    argv.extend(["--employee-status", employee_status])
    _opt_list(argv, "--tables", tables)
    _opt(argv, "--output-dir", output_dir)
    argv.extend(["--mode", mode])
    argv.extend(["--parallel", str(parallel)])
    if reset_all_checkpoints:
        argv.append("--reset-checkpoints")
    elif reset_checkpoints:
        argv.append("--reset-checkpoints")
        argv.extend(reset_checkpoints)
    _flag(argv, "--dry-run", dry_run)
    _flag(argv, "--verbose", verbose)
    return argv


def build_upload_factorial_argv(
    *,
    output_dir: str = "./exports_factorial",
    tables: Optional[Sequence[str]] = None,
    dry_run: bool = False,
    skip_existing: bool = False,
    verbose: bool = False,
) -> List[str]:
    argv: List[str] = ["--output-dir", output_dir]
    _opt_list(argv, "--tables", tables)
    _flag(argv, "--dry-run", dry_run)
    _flag(argv, "--skip-existing", skip_existing)
    _flag(argv, "--verbose", verbose)
    return argv


# --------------------------------------------------------------------------------------
# argv builders — HubSpot CRM
# --------------------------------------------------------------------------------------


def build_extract_hubspot_argv(
    *,
    tables: Optional[Sequence[str]] = None,
    output_dir: str = "",
    parallel: int = 1,
    dry_run: bool = False,
    verbose: bool = False,
) -> List[str]:
    argv: List[str] = []
    _opt_list(argv, "--tables", tables)
    _opt(argv, "--output-dir", output_dir)
    argv.extend(["--parallel", str(parallel)])
    _flag(argv, "--dry-run", dry_run)
    _flag(argv, "--verbose", verbose)
    return argv


def build_upload_hubspot_argv(
    *,
    output_dir: str = "./exports_hubspot",
    tables: Optional[Sequence[str]] = None,
    dry_run: bool = False,
    skip_existing: bool = False,
    verbose: bool = False,
) -> List[str]:
    argv: List[str] = ["--output-dir", output_dir]
    _opt_list(argv, "--tables", tables)
    _flag(argv, "--dry-run", dry_run)
    _flag(argv, "--skip-existing", skip_existing)
    _flag(argv, "--verbose", verbose)
    return argv


# --------------------------------------------------------------------------------------
# argv builders — Fabric Data Factory pipelines
# --------------------------------------------------------------------------------------


def build_run_pipeline_argv(
    *,
    pipeline: str,
    wait: bool = True,
    poll_seconds: int = 15,
    verbose: bool = False,
) -> List[str]:
    argv: List[str] = ["--pipeline", pipeline]
    if not wait:
        argv.append("--no-wait")
    argv.extend(["--poll-seconds", str(poll_seconds)])
    _flag(argv, "--verbose", verbose)
    return argv


# --------------------------------------------------------------------------------------
# Per-table/per-file status, reconstructed from the captured log text.
#
# The backend doesn't return structured per-table results (run_exports/run_extract
# only return aggregate counts), so this reads the same log messages a human
# would to answer "which tables ran and how did each one go?". If a message
# format ever changes, the worst case is a table showing as "unknown" — never
# a wrong success/failure claim.
# --------------------------------------------------------------------------------------

_STATUS_OK, _STATUS_SKIPPED, _STATUS_DRY_RUN, _STATUS_ERROR, _STATUS_UNKNOWN, _STATUS_IN_PROGRESS = (
    "ok",
    "skipped",
    "dry_run",
    "error",
    "unknown",
    "in_progress",
)


def _export_table_outcome(name: str, log: str) -> Optional[TableStatus]:
    """Matches src/bc_client/exporter.py's export_table(), shared by BC and Factorial."""
    escaped = re.escape(name)
    m = re.search(rf"Table '{escaped}' export complete; (\d+) rows written", log)
    if m:
        return TableStatus(name=name, status=_STATUS_OK, detail=f"{m.group(1)} filas")
    if re.search(rf"Table '{escaped}' returned no rows; creating empty file", log):
        return TableStatus(name=name, status=_STATUS_OK, detail="0 filas (fichero vacío)")
    return None


def parse_bc_extract_tables(expected: Sequence[str], log: str, *, finished: bool = True) -> List[TableStatus]:
    statuses: List[TableStatus] = []
    for name in expected:
        if f"would export table '{name}'" in log:
            statuses.append(TableStatus(name=name, status=_STATUS_DRY_RUN, detail="simulación"))
            continue
        if f"Table '{name}': no new rows; skipping CSV creation" in log:
            statuses.append(TableStatus(name=name, status=_STATUS_SKIPPED, detail="sin filas nuevas"))
            continue
        outcome = _export_table_outcome(name, log)
        if outcome:
            statuses.append(outcome)
            continue
        if f"Exporting table '{name}'" in log:
            # Seen mid-export with no completion line yet. While the task is
            # still running this is completely normal (especially with
            # --parallel > 1, where several tables are simultaneously "started
            # but not finished") -- only call it an error once the process has
            # actually exited without ever confirming this table.
            if finished:
                statuses.append(
                    TableStatus(name=name, status=_STATUS_ERROR, detail="empezó pero no se confirmó su finalización")
                )
            else:
                statuses.append(TableStatus(name=name, status=_STATUS_IN_PROGRESS, detail="exportando…"))
            continue
        statuses.append(TableStatus(name=name, status=_STATUS_UNKNOWN, detail="no llegó a procesarse"))
    return statuses


def parse_factorial_extract_tables(expected: Sequence[str], log: str, *, finished: bool = True) -> List[TableStatus]:
    statuses: List[TableStatus] = []
    for name in expected:
        if f"Would write '{name}'" in log:
            statuses.append(TableStatus(name=name, status=_STATUS_DRY_RUN, detail="simulación"))
            continue
        outcome = _export_table_outcome(name, log)
        if outcome:
            statuses.append(outcome)
            continue
        if f"Fetching '{name}'" in log:
            # Same rationale as parse_bc_extract_tables above.
            if finished:
                statuses.append(
                    TableStatus(name=name, status=_STATUS_ERROR, detail="empezó pero no se confirmó su finalización")
                )
            else:
                statuses.append(TableStatus(name=name, status=_STATUS_IN_PROGRESS, detail="obteniendo datos…"))
            continue
        statuses.append(TableStatus(name=name, status=_STATUS_UNKNOWN, detail="no llegó a procesarse"))
    return statuses


def parse_hubspot_extract_tables(expected: Sequence[str], log: str, *, finished: bool = True) -> List[TableStatus]:
    statuses: List[TableStatus] = []
    for name in expected:
        if f"Would write '{name}'" in log:
            statuses.append(TableStatus(name=name, status=_STATUS_DRY_RUN, detail="simulación"))
            continue
        outcome = _export_table_outcome(name, log)
        if outcome:
            statuses.append(outcome)
            continue
        if f"Fetching '{name}'" in log:
            # Same rationale as parse_bc_extract_tables above.
            if finished:
                statuses.append(
                    TableStatus(name=name, status=_STATUS_ERROR, detail="empezó pero no se confirmó su finalización")
                )
            else:
                statuses.append(TableStatus(name=name, status=_STATUS_IN_PROGRESS, detail="obteniendo datos…"))
            continue
        statuses.append(TableStatus(name=name, status=_STATUS_UNKNOWN, detail="no llegó a procesarse"))
    return statuses


_UPLOAD_ATTEMPT_RE = re.compile(r"Uploading '([^']+)' to Fabric OneLake\.\.\.")
_UPLOAD_DRYRUN_RE = re.compile(r"\[dry-run\] Would upload: (\S+)")


def parse_upload_files(log: str) -> List[TableStatus]:
    """Derives the list of processed files directly from the log (order of upload)."""
    statuses: List[TableStatus] = []
    for name in dict.fromkeys(_UPLOAD_ATTEMPT_RE.findall(log)):
        escaped = re.escape(name)
        if re.search(rf"Successfully uploaded '{escaped}'", log):
            statuses.append(TableStatus(name=name, status=_STATUS_OK, detail="subido"))
        elif re.search(rf"Skipping '{escaped}' because it already exists", log):
            statuses.append(TableStatus(name=name, status=_STATUS_SKIPPED, detail="ya existía en OneLake"))
        elif re.search(rf"Upload failed for '[^']*{escaped}'", log):
            statuses.append(TableStatus(name=name, status=_STATUS_ERROR, detail="fallo al subir"))
        else:
            statuses.append(TableStatus(name=name, status=_STATUS_UNKNOWN, detail="resultado no confirmado"))
    for name in dict.fromkeys(_UPLOAD_DRYRUN_RE.findall(log)):
        statuses.append(TableStatus(name=name, status=_STATUS_DRY_RUN, detail="simulación"))
    return statuses


def merge_sync_statuses(
    extract_statuses: List[TableStatus], upload_statuses: List[TableStatus]
) -> List[TableStatus]:
    """A sync task extracts a table to CSV, then uploads that same CSV --
    one table, two phases. Concatenating extract_statuses + upload_statuses
    (the previous behavior) showed two separate cards for the same table, one
    per phase; this folds the upload outcome into the extract entry as a
    second status instead, so the UI can show one card per table with an
    extra icon for "subido / pendiente de subir / error al subir".

    Matches upload entries back to their table by stripping the ".csv" upload
    filenames carry (parse_upload_files() names entries after the uploaded
    file, e.g. "customers.csv", while parse_*_extract_tables() names them
    after the table, e.g. "customers").
    """
    upload_by_table = {(u.name[:-4] if u.name.endswith(".csv") else u.name): u for u in upload_statuses}

    merged: List[TableStatus] = []
    for e in extract_statuses:
        upload = upload_by_table.get(e.name)
        if upload is not None:
            upload_status, upload_detail = upload.status, upload.detail
        elif e.status == _STATUS_OK:
            # Extracted successfully but the upload phase hasn't reached (or
            # logged anything about) this table yet.
            upload_status, upload_detail = "pending", "pendiente de subir"
        else:
            # Never extracted (error/unknown/dry_run/skipped) -- nothing to
            # upload yet, and no upload icon to show for it.
            upload_status, upload_detail = None, ""
        merged.append(
            TableStatus(
                name=e.name,
                status=e.status,
                detail=e.detail,
                upload_status=upload_status,
                upload_detail=upload_detail,
            )
        )
    return merged


# --------------------------------------------------------------------------------------
# UI helpers (read-only; never require secrets, so forms can render before any run)
# --------------------------------------------------------------------------------------


def list_bc_tables() -> List[str]:
    # Reads table_configs's own (monkeypatchable-in-tests) path variable
    # rather than recomputing it here, so this and table_configs.py's
    # add/delete functions can never point at two different files.
    return _list_table_names(table_configs._BC_TABLES_PATH)


def list_factorial_tables() -> List[str]:
    return _list_table_names(table_configs._FACTORIAL_TABLES_PATH)


def list_hubspot_tables() -> List[str]:
    return _list_table_names(table_configs._HUBSPOT_TABLES_PATH)


def _list_table_names(path: Path) -> List[str]:
    if not path.is_file():
        return []
    # Every request that renders a table picker calls this; caching on
    # (path, mtime) avoids re-reading and re-parsing the YAML from disk each
    # time, while still picking up an edit on the very next call (mtime
    # changes -> cache key changes) instead of requiring a process restart.
    return _list_table_names_cached(str(path), path.stat().st_mtime)


@lru_cache(maxsize=32)
def _list_table_names_cached(path_str: str, mtime: float) -> List[str]:
    path = Path(path_str)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return []
    tables = data.get("tables") if isinstance(data, dict) else None
    if not isinstance(tables, list):
        return []
    return sorted(t.get("name") for t in tables if isinstance(t, dict) and t.get("name"))


_CONFIG_DEFAULTS_CACHE: Optional[dict] = None


def config_defaults() -> dict:
    """Best-effort read of config.json for pre-filling form defaults. Never raises."""
    global _CONFIG_DEFAULTS_CACHE
    if _CONFIG_DEFAULTS_CACHE is None:
        try:
            data, _root = load_config_data()
        except Exception:
            data = {}
        _CONFIG_DEFAULTS_CACHE = data
    return _CONFIG_DEFAULTS_CACHE


def list_fabric_pipelines() -> List[str]:
    """Best-effort read of config.json's fabric_pipelines.pipelines names. Never raises."""
    section = config_defaults().get("fabric_pipelines")
    if not isinstance(section, dict):
        return []
    pipelines = section.get("pipelines")
    if not isinstance(pipelines, list):
        return []
    return [p["name"] for p in pipelines if isinstance(p, dict) and p.get("name")]
