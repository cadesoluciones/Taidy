# -*- coding: utf-8 -*-
"""
Subprocess-based task engine.

Each run (manual click or scheduled tick) launches the *exact same CLI* a
person would type in a terminal — e.g. `python -m src.main --mode full` — as
a separate OS process, exactly like `task extract:bc` already does. Nothing
in src/** is touched or imported for execution.

This is what makes "stop a running task" possible without any cooperative
cancellation hook inside the backend's per-table loops: stopping is just
terminating the child process. It's also what lets two independent tasks
(e.g. a BC extract and a Factorial extract) genuinely run at the same time
instead of being serialized behind one in-process lock.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from webapp import adapter, history, notifications  # noqa: E402

MODULE_FOR_ACTION = {
    "extract_bc": "src.main",
    "upload_bc": "src.fabric_upload.cli",
    "extract_factorial": "src.factorial_main",
    "upload_factorial": "src.factorial_client.push",
    "run_pipeline": "src.fabric_pipelines.cli",
}

ACTION_LABELS = {
    "extract_bc": "BC · Extraer",
    "upload_bc": "BC · Subir",
    "sync_bc": "BC · Sync (extraer + subir)",
    "extract_factorial": "Factorial · Extraer",
    "upload_factorial": "Factorial · Subir",
    "sync_factorial": "Factorial · Sync (extraer + subir)",
    "run_pipeline": "Fabric · Ejecutar pipeline",
}

# Actions that touch the same CSV/checkpoint files and must not run concurrently.
_CONFLICT_GROUPS = {
    "extract_bc": {"extract_bc", "sync_bc"},
    "upload_bc": {"upload_bc", "sync_bc"},
    "sync_bc": {"extract_bc", "upload_bc", "sync_bc"},
    "extract_factorial": {"extract_factorial", "sync_factorial"},
    "upload_factorial": {"upload_factorial", "sync_factorial"},
    "sync_factorial": {"extract_factorial", "upload_factorial", "sync_factorial"},
}

_STOP_GRACE_SECONDS = 5
_MAX_FINISHED_IN_MEMORY = 50


def task_action_label(task: "Task") -> str:
    """ACTION_LABELS' generic label is ambiguous for run_pipeline -- several
    different pipelines all show up as just "Fabric · Ejecutar pipeline"
    otherwise. resource_key already carries the pipeline name (see launch()'s
    f"run_pipeline:{pipeline}"), so pull it back out instead of threading a
    separate field through Task/TaskOut."""
    label = ACTION_LABELS.get(task.action, task.action)
    if task.action == "run_pipeline" and ":" in task.resource_key:
        pipeline = task.resource_key.split(":", 1)[1]
        return f"{label} ({pipeline})"
    return label


@dataclass
class Task:
    id: str
    action: str
    triggered_by: str  # e.g. "alice@corp.com" or "programada: Nombre de la tarea"
    started_at: str
    resource_key: str = ""  # what this task exclusively holds while running; defaults to `action`
    step_labels: List[str] = field(default_factory=lambda: ["run"])
    expected_tables: List[str] = field(default_factory=list)
    finished_at: Optional[str] = None
    status: str = "running"  # running | stopping | ok | error | stopped
    return_code: Optional[int] = None
    current_step: int = 0
    notify: bool = False
    _log_parts: List[str] = field(default_factory=list, repr=False, compare=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)
    _process: Optional[subprocess.Popen] = field(default=None, repr=False, compare=False)

    def _append_log(self, text: str) -> None:
        with self._lock:
            self._log_parts.append(text)

    def log(self) -> str:
        with self._lock:
            return adapter.strip_ansi("".join(self._log_parts))

    def duration_seconds(self) -> float:
        start = datetime.fromisoformat(self.started_at)
        end = datetime.fromisoformat(self.finished_at) if self.finished_at else datetime.now(timezone.utc)
        return (end - start).total_seconds()

    def log_tail(self, chars: int = 4000) -> str:
        """Last `chars` of the log -- for actions with no per-table
        breakdown (run_pipeline just logs status transitions as plain
        lines), this is the only way to see progress while it's running."""
        text = self.log()
        return text[-chars:]

    def table_statuses(self):
        log_text = self.log()
        # A table "started but not yet confirmed finished" is completely normal
        # while this task is still running (see adapter.py's `finished` param) —
        # only treat it as an error once the process has actually exited.
        finished = self.status in ("ok", "error", "stopped")
        if self.action == "extract_bc":
            return adapter.parse_bc_extract_tables(self.expected_tables, log_text, finished=finished)
        if self.action == "extract_factorial":
            return adapter.parse_factorial_extract_tables(self.expected_tables, log_text, finished=finished)
        if self.action in ("upload_bc", "upload_factorial"):
            return adapter.parse_upload_files(log_text)
        if self.action in ("sync_bc", "sync_factorial"):
            parser = adapter.parse_bc_extract_tables if self.action == "sync_bc" else adapter.parse_factorial_extract_tables
            extract_statuses = parser(self.expected_tables, log_text, finished=finished)
            upload_statuses = adapter.parse_upload_files(log_text)
            return adapter.merge_sync_statuses(extract_statuses, upload_statuses)
        return []


_REGISTRY: Dict[str, Task] = {}
_REGISTRY_LOCK = threading.Lock()


def list_tasks() -> List[Task]:
    with _REGISTRY_LOCK:
        tasks = list(_REGISTRY.values())
    return sorted(tasks, key=lambda t: t.started_at, reverse=True)


def get_task(task_id: str) -> Optional[Task]:
    with _REGISTRY_LOCK:
        return _REGISTRY.get(task_id)


def _register(task: Task) -> None:
    with _REGISTRY_LOCK:
        _REGISTRY[task.id] = task
        finished = sorted(
            (t for t in _REGISTRY.values() if t.status not in ("running", "stopping")),
            key=lambda t: t.finished_at or "",
        )
        overflow = len(finished) - _MAX_FINISHED_IN_MEMORY
        for old in finished[:max(overflow, 0)]:
            _REGISTRY.pop(old.id, None)


def conflicting_task_running(action: str, resource_key: Optional[str] = None) -> Optional[Task]:
    """Two tasks conflict if they'd touch the same files (grouped by action) — except
    run_pipeline, where only the SAME pipeline (by resource_key) conflicts with itself;
    two different pipelines don't touch anything of each other's and may run together.
    """
    if action == "run_pipeline":
        key = resource_key or action
        with _REGISTRY_LOCK:
            for t in _REGISTRY.values():
                if t.status in ("running", "stopping") and (t.resource_key or t.action) == key:
                    return t
        return None

    conflicts = _CONFLICT_GROUPS.get(action, {action})
    with _REGISTRY_LOCK:
        for t in _REGISTRY.values():
            if t.action in conflicts and t.status in ("running", "stopping"):
                return t
    return None


def _popen(module: str, argv: List[str]) -> subprocess.Popen:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_PROJECT_ROOT)
    # Rich forces "terminal" rendering even on a redirected pipe; without a
    # wide-enough COLUMNS it wraps at ~80 chars, which can split a table name
    # across lines and break the log parsing in adapter.py. 300 comfortably
    # covers the longest real log lines (full BC OData URLs) without Rich
    # padding every short line out to a wasteful width.
    env["COLUMNS"] = "300"
    env["LINES"] = "50"
    return subprocess.Popen(
        [sys.executable, "-m", module, *argv],
        cwd=str(_PROJECT_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )


def _pump_output(task: Task, proc: subprocess.Popen) -> None:
    try:
        for line in proc.stdout:
            # Rich pads short lines out to the full console width with
            # trailing spaces *before* the newline; strip those so stored
            # logs stay compact and readable (rstrip alone won't reach past
            # a trailing "\n").
            task._append_log(line.rstrip("\n").rstrip(" \t") + "\n")
    finally:
        proc.wait()


def _finalize(task: Task, return_code: int) -> None:
    task.return_code = return_code
    task.finished_at = datetime.now(timezone.utc).isoformat()
    task.status = "stopped" if task.status == "stopping" else ("ok" if return_code == 0 else "error")
    if task.status == "ok":
        message = "Completado correctamente."
    elif task.status == "stopped":
        message = "Detenida por el usuario."
    else:
        message = f"Terminó con código de salida {return_code}. Revisa el log."
    history.record_run(
        action=task.action,
        source=task.triggered_by,
        status=task.status,
        ok=task.status == "ok",
        message=message,
        log=task.log(),
        duration_seconds=task.duration_seconds(),
    )
    if task.notify:
        notifications.notify_task_finished(
            action_label=task_action_label(task),
            triggered_by=task.triggered_by,
            status=task.status,
            message=message,
        )


def start_task(
    *,
    action: str,
    argv: List[str],
    triggered_by: str,
    expected_tables: Optional[List[str]] = None,
    resource_key: Optional[str] = None,
    notify: bool = False,
) -> Task:
    """Launches a single-step action (extract_bc, upload_bc, extract_factorial, upload_factorial, run_pipeline)."""
    blocker = conflicting_task_running(action, resource_key)
    if blocker is not None:
        raise RuntimeError(
            f"Ya hay una tarea de '{ACTION_LABELS.get(blocker.action, blocker.action)}' en curso. "
            "Espera a que termine o detenla primero."
        )

    module = MODULE_FOR_ACTION[action]
    task = Task(
        id=uuid.uuid4().hex,
        action=action,
        triggered_by=triggered_by,
        started_at=datetime.now(timezone.utc).isoformat(),
        resource_key=resource_key or action,
        expected_tables=list(expected_tables or []),
        notify=notify,
    )
    _register(task)

    def _worker() -> None:
        proc = _popen(module, argv)
        with task._lock:
            task._process = proc
        _pump_output(task, proc)
        _finalize(task, proc.returncode)

    threading.Thread(target=_worker, daemon=True, name=f"task-{task.id}").start()
    return task


def start_sync_task(
    *,
    action: str,
    steps: List[Tuple[str, List[str], str]],  # (module, argv, step_label)
    triggered_by: str,
    expected_tables: Optional[List[str]] = None,
    notify: bool = False,
) -> Task:
    """Launches a two-step action (sync_bc, sync_factorial) as sequential subprocesses."""
    blocker = conflicting_task_running(action)
    if blocker is not None:
        raise RuntimeError(
            f"Ya hay una tarea de '{ACTION_LABELS.get(blocker.action, blocker.action)}' en curso. "
            "Espera a que termine o detenla primero."
        )

    task = Task(
        id=uuid.uuid4().hex,
        action=action,
        triggered_by=triggered_by,
        started_at=datetime.now(timezone.utc).isoformat(),
        step_labels=[label for _, _, label in steps],
        expected_tables=list(expected_tables or []),
        notify=notify,
    )
    _register(task)

    def _worker() -> None:
        resolved_output_dir: Optional[str] = None
        for index, (module, argv, label) in enumerate(steps):
            if task.status == "stopping":
                break
            task.current_step = index
            step_argv = _replace_output_dir(argv, resolved_output_dir) if label == "subir" and resolved_output_dir else argv
            proc = _popen(module, step_argv)
            with task._lock:
                task._process = proc
            _pump_output(task, proc)
            if label == "extraer":
                # BC's extract resolves a run-specific subfolder (full/ or
                # incremental/<timestamp>/) that isn't knowable beforehand;
                # the upload step must target that exact folder.
                resolved_output_dir = _extract_output_dir_from_log(task.log()) or resolved_output_dir
            if proc.returncode != 0:
                _finalize(task, proc.returncode)
                return
        _finalize(task, 0)

    threading.Thread(target=_worker, daemon=True, name=f"task-{task.id}").start()
    return task


_OUTPUT_DIR_LOG_RE = re.compile(r"Writing CSVs to (.+)")


def _extract_output_dir_from_log(log_text: str) -> Optional[str]:
    match = _OUTPUT_DIR_LOG_RE.search(log_text)
    return match.group(1).strip() if match else None


def _replace_output_dir(argv: List[str], new_dir: str) -> List[str]:
    argv = list(argv)
    if "--output-dir" in argv:
        idx = argv.index("--output-dir")
        argv[idx + 1] = new_dir
    else:
        argv = argv + ["--output-dir", new_dir]
    return argv


def stop_task(task_id: str) -> bool:
    """Requests a stop. Returns False if the task doesn't exist or already finished."""
    task = get_task(task_id)
    if task is None or task.status not in ("running",):
        return False
    task.status = "stopping"

    with task._lock:
        proc = task._process

    if proc is None or proc.poll() is not None:
        return True

    try:
        proc.terminate()
    except Exception:
        pass

    def _escalate() -> None:
        try:
            proc.wait(timeout=_STOP_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except Exception:
                pass

    threading.Thread(target=_escalate, daemon=True).start()
    return True


# --------------------------------------------------------------------------------------
# Single dispatch point: "action name + params dict" -> the right argv builder(s) + launch.
# Used identically by manual runs (api/routers/tasks.py) and scheduled runs
# (webapp/scheduler.py) so both go through the exact same code path and show
# up the same way in "Tareas en curso".
# --------------------------------------------------------------------------------------


def launch(action: str, params: dict, triggered_by: str) -> Task:
    params = dict(params or {})
    notify = bool(params.pop("notify", False))
    tables = params.get("tables")

    if action in ("extract_factorial", "sync_factorial") and not (params.get("start_on") and params.get("end_on")):
        raise ValueError("'Desde' y 'Hasta' son obligatorios para Factorial.")

    if action == "extract_bc":
        argv = adapter.build_extract_bc_argv(**params)
        expected = list(tables) if tables else adapter.list_bc_tables()
        return start_task(action=action, argv=argv, triggered_by=triggered_by, expected_tables=expected, notify=notify)

    if action == "upload_bc":
        argv = adapter.build_upload_bc_argv(**params)
        return start_task(action=action, argv=argv, triggered_by=triggered_by, notify=notify)

    if action == "run_pipeline":
        if not params.get("pipeline"):
            raise ValueError("Indica qué pipeline lanzar.")
        argv = adapter.build_run_pipeline_argv(**params)
        return start_task(
            action=action,
            argv=argv,
            triggered_by=triggered_by,
            resource_key=f"run_pipeline:{params['pipeline']}",
            notify=notify,
        )

    if action == "extract_factorial":
        argv = adapter.build_extract_factorial_argv(**params)
        expected = list(tables) if tables else adapter.list_factorial_tables()
        return start_task(action=action, argv=argv, triggered_by=triggered_by, expected_tables=expected, notify=notify)

    if action == "upload_factorial":
        argv = adapter.build_upload_factorial_argv(**params)
        return start_task(action=action, argv=argv, triggered_by=triggered_by, notify=notify)

    if action == "sync_bc":
        output_dir = params.get("output_dir") or "./exports"
        extract_argv = adapter.build_extract_bc_argv(
            tables=tables,
            output_dir=output_dir,
            mode=params.get("mode", "incremental"),
            parallel=params.get("parallel", 1),
            dry_run=params.get("dry_run", False),
            verbose=params.get("verbose", False),
        )
        upload_argv = adapter.build_upload_bc_argv(
            output_dir=output_dir,
            dry_run=params.get("dry_run", False),
            skip_existing=params.get("skip_existing", False),
            verbose=params.get("verbose", False),
        )
        expected = list(tables) if tables else adapter.list_bc_tables()
        return start_sync_task(
            action=action,
            steps=[
                (MODULE_FOR_ACTION["extract_bc"], extract_argv, "extraer"),
                (MODULE_FOR_ACTION["upload_bc"], upload_argv, "subir"),
            ],
            triggered_by=triggered_by,
            expected_tables=expected,
            notify=notify,
        )

    if action == "sync_factorial":
        output_dir = params.get("output_dir") or "./exports_factorial"
        extract_argv = adapter.build_extract_factorial_argv(
            start_on=params["start_on"],
            end_on=params["end_on"],
            employees=params.get("employees"),
            employee_status=params.get("employee_status", "active"),
            tables=tables,
            output_dir=output_dir,
            mode=params.get("mode", "full"),
            parallel=params.get("parallel", 1),
            reset_checkpoints=params.get("reset_checkpoints"),
            reset_all_checkpoints=params.get("reset_all_checkpoints", False),
            dry_run=params.get("dry_run", False),
            verbose=params.get("verbose", False),
        )
        upload_argv = adapter.build_upload_factorial_argv(
            output_dir=output_dir,
            tables=tables,
            dry_run=params.get("dry_run", False),
            skip_existing=params.get("skip_existing", False),
            verbose=params.get("verbose", False),
        )
        expected = list(tables) if tables else adapter.list_factorial_tables()
        return start_sync_task(
            action=action,
            steps=[
                (MODULE_FOR_ACTION["extract_factorial"], extract_argv, "extraer"),
                (MODULE_FOR_ACTION["upload_factorial"], upload_argv, "subir"),
            ],
            triggered_by=triggered_by,
            expected_tables=expected,
            notify=notify,
        )

    raise ValueError(f"Acción desconocida: {action}")
