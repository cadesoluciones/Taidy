# -*- coding: utf-8 -*-
"""
Workflow definitions: named DAGs of existing actions (extract/upload/sync/
run_pipeline). Each step declares what it depends on and what to do if a
dependency didn't succeed (trigger_rule). This module only owns the
persisted *definition* (CRUD + diagram rendering); actually running one
lives in webapp/workflow_engine.py.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

TRIGGER_ALL_SUCCESS = "all_success"  # only run once every dependency succeeded
TRIGGER_ALWAYS = "always"  # run regardless of how dependencies ended

TRIGGER_LABELS = {
    TRIGGER_ALL_SUCCESS: "Solo si todas sus dependencias tuvieron éxito",
    TRIGGER_ALWAYS: "Aunque alguna dependencia haya fallado",
}

_WORKFLOWS_PATH = Path(__file__).resolve().parent / "workflows.json"
_LOCK = threading.Lock()

# Every value below was checked against black (#000000) text with the WCAG 2.2
# contrast formula and clears the 4.5:1 AA minimum (lowest is "error" at 5.67:1) —
# see audit finding A-02. fontcolor is set explicitly in to_dot() below so this
# stays true regardless of Graphviz's own default, which isn't guaranteed.
_STATUS_COLORS = {
    "pending": "#d0d0d0",
    "running": "#4a90d9",
    "ok": "#3fb950",
    "error": "#e5534b",
    "cancelled": "#9e9e9e",
    "stopped": "#c9a227",
}
_NODE_FONT_COLOR = "#000000"


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


def to_dot(steps: List[dict], *, step_status: Optional[Dict[str, str]] = None) -> str:
    """Renders the DAG as Graphviz DOT source (rendered client-side by Streamlit
    via st.graphviz_chart — no system Graphviz binary needed on the server).
    """
    lines = [
        "digraph {",
        "  rankdir=LR;",
        f'  node [shape=box, style=filled, fontname="Arial", fontcolor="{_NODE_FONT_COLOR}"];',
    ]
    for s in steps:
        status = (step_status or {}).get(s["id"], "pending")
        color = _STATUS_COLORS.get(status, "#ffffff")
        label = (s.get("label") or s["id"]).replace('"', "'")
        node_label = f"{label}\\n({status})" if step_status is not None else label
        lines.append(f'  "{s["id"]}" [label="{node_label}", fillcolor="{color}"];')
    for s in steps:
        for dep in s.get("depends_on", []):
            style = "solid" if s.get("trigger_rule", TRIGGER_ALL_SUCCESS) == TRIGGER_ALL_SUCCESS else "dashed"
            lines.append(f'  "{dep}" -> "{s["id"]}" [style={style}];')
    lines.append("}")
    return "\n".join(lines)
