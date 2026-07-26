# -*- coding: utf-8 -*-
"""
Natural-language activity summary -- two interchangeable ways to produce it:
a deterministic template (default: no external dependency, no cost, no data
ever leaves the network) or an LLM-generated one (opt-in, see
webapp/llm_providers.py). Both consume the exact same history/alerts data;
the LLM path only changes how it gets turned into prose.
"""

from __future__ import annotations

from typing import List, Optional

from webapp import alerts as alerts_module
from webapp import llm_providers
from webapp.tasks import ACTION_LABELS


def _action_label(action: str) -> str:
    if action == "run_workflow":
        return "Flujo"
    return ACTION_LABELS.get(action, action)


def build_template_summary(entries: List[dict], alert_list: Optional[List[dict]] = None) -> str:
    """entries: newest-first history entries (see webapp/history.get_history)."""
    if not entries:
        return "Todavía no se ha registrado ninguna ejecución."

    if alert_list is None:
        alert_list = alerts_module.detect_elevated_error_rates(entries)

    ok_count = sum(1 for e in entries if e["ok"])
    error_count = sum(1 for e in entries if not e["ok"] and e.get("status") != "stopped")
    stopped_count = sum(1 for e in entries if e.get("status") == "stopped")

    counts = f"{ok_count} correcta{'s' if ok_count != 1 else ''}, {error_count} con error"
    if stopped_count:
        counts += f", {stopped_count} detenida{'s' if stopped_count != 1 else ''} manualmente"
    parts = [f"En las últimas {len(entries)} ejecuciones registradas: {counts}."]

    latest = entries[0]
    if latest.get("status") == "stopped":
        outcome = "detenida manualmente"
    elif latest["ok"]:
        outcome = "resultado correcto"
    else:
        outcome = "con error"
    parts.append(f"La ejecución más reciente fue '{_action_label(latest['action'])}' ({latest['source']}), {outcome}.")

    for a in alert_list:
        parts.append(
            f"Aviso: '{_action_label(a['action'])}' tiene una tasa de error elevada "
            f"({a['recent_failures']} de {a['recent_total']} ejecuciones recientes han fallado)."
        )

    return " ".join(parts)


def _build_llm_prompt(entries: List[dict], alert_list: List[dict]) -> str:
    lines = [
        "Eres un asistente que resume brevemente, en español y en un único párrafo corto, "
        "la actividad reciente de un sistema de extracción de datos (Business Central, "
        "Factorial HR, Microsoft Fabric). No inventes datos que no aparezcan abajo.",
        "",
        "Ejecuciones recientes (de la más reciente a la más antigua):",
    ]
    for e in entries[:20]:
        status = "detenida" if e.get("status") == "stopped" else ("correcta" if e["ok"] else "error")
        lines.append(f"- {_action_label(e['action'])} · {e['source']} · {status} · {e['finished_at']}")

    if alert_list:
        lines.append("")
        lines.append("Avisos de tasa de error elevada:")
        for a in alert_list:
            lines.append(f"- {_action_label(a['action'])}: {a['recent_failures']} de {a['recent_total']} fallidas")

    return "\n".join(lines)


def build_summary(entries: List[dict], *, use_llm: bool) -> tuple[str, str]:
    """Returns (text, mode_used) where mode_used is "llm" or "template" --
    "llm" was requested falls back to "template" (never raises) whenever the
    LLM path isn't configured or the call itself fails, so the dashboard
    always has something to show.
    """
    alert_list = alerts_module.detect_elevated_error_rates(entries)

    if use_llm:
        try:
            text = llm_providers.generate_narrative_summary(_build_llm_prompt(entries, alert_list))
            return text, "llm"
        except llm_providers.LlmError:
            pass

    return build_template_summary(entries, alert_list), "template"
