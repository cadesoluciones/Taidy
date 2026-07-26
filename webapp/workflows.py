# -*- coding: utf-8 -*-
"""
Workflow definitions: named DAGs of existing actions (extract/upload/sync/
run_pipeline). Each step declares what it depends on and what to do if a
dependency didn't succeed (trigger_rule). This module only owns the
persisted *definition* (CRUD); actually running one lives in
webapp/workflow_engine.py. The interactive diagram is rendered client-side
by the React frontend (@xyflow/react) from this same step data.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from webapp.state_dir import state_path

TRIGGER_ALL_SUCCESS = "all_success"  # only run once every dependency succeeded
TRIGGER_ALWAYS = "always"  # run regardless of how dependencies ended

TRIGGER_LABELS = {
    TRIGGER_ALL_SUCCESS: "Solo si todas sus dependencias tuvieron éxito",
    TRIGGER_ALWAYS: "Aunque alguna dependencia haya fallado",
}

_WORKFLOWS_PATH = state_path("workflows.json", Path(__file__).resolve().parent)
_LOCK = threading.Lock()


def _read() -> list:
    if not _WORKFLOWS_PATH.exists():
        return []
    try:
        return json.loads(_WORKFLOWS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def _write(data: list) -> None:
    tmp = _WORKFLOWS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(_WORKFLOWS_PATH)


def list_workflows() -> List[dict]:
    with _LOCK:
        return _read()


def get_workflow(workflow_id: str) -> Optional[dict]:
    return next((w for w in list_workflows() if w["id"] == workflow_id), None)


def _validate_steps(steps: List[dict]) -> None:
    if not steps:
        raise ValueError("Un flujo necesita al menos un bloque.")

    ids = [s["id"] for s in steps]
    if len(ids) != len(set(ids)):
        raise ValueError("Hay bloques con el mismo identificador interno.")
    id_set = set(ids)

    for s in steps:
        for dep in s.get("depends_on", []):
            if dep == s["id"]:
                raise ValueError(f"El bloque '{s['label']}' no puede depender de sí mismo.")
            if dep not in id_set:
                raise ValueError(f"El bloque '{s['label']}' depende de un bloque que no existe.")

    # Cycle detection (Kahn's algorithm): if we can't reduce every node's
    # indegree to 0 by repeatedly removing sources, there's a cycle.
    indegree = {s["id"]: 0 for s in steps}
    graph: Dict[str, List[str]] = {s["id"]: [] for s in steps}
    for s in steps:
        for dep in s.get("depends_on", []):
            graph[dep].append(s["id"])
            indegree[s["id"]] += 1
    queue = [sid for sid, deg in indegree.items() if deg == 0]
    visited = 0
    while queue:
        node = queue.pop()
        visited += 1
        for nxt in graph[node]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)
    if visited != len(steps):
        raise ValueError("El flujo tiene una dependencia circular entre bloques.")


def create_workflow(name: str, steps: List[dict]) -> dict:
    name = name.strip()
    if not name:
        raise ValueError("El flujo necesita un nombre.")
    _validate_steps(steps)
    workflow = {
        "id": uuid.uuid4().hex,
        "name": name,
        "steps": steps,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with _LOCK:
        data = _read()
        data.append(workflow)
        _write(data)
    return workflow


def update_workflow(workflow_id: str, name: str, steps: List[dict]) -> dict:
    """Overwrites an existing workflow's name/steps in place -- same
    validation as create_workflow(), but keeps the original `id` and
    `created_at` so scheduled entries and past run history that reference
    this workflow_id stay valid after the edit."""
    name = name.strip()
    if not name:
        raise ValueError("El flujo necesita un nombre.")
    _validate_steps(steps)
    with _LOCK:
        data = _read()
        existing = next((w for w in data if w["id"] == workflow_id), None)
        if existing is None:
            raise ValueError(f"Flujo desconocido: {workflow_id}")
        existing["name"] = name
        existing["steps"] = steps
        _write(data)
        return existing


def delete_workflow(workflow_id: str) -> None:
    with _LOCK:
        data = _read()
        data = [w for w in data if w["id"] != workflow_id]
        _write(data)
