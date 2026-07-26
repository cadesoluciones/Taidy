# -*- coding: utf-8 -*-
"""
webapp/summary.build_summary() must always return something usable: the
template path has zero external dependencies and can't fail, and a
requested-but-unavailable/failing LLM path falls back to it silently rather
than ever erroring the dashboard out.
"""

from __future__ import annotations

from typing import Optional

from webapp import llm_providers, summary


def _entry(
    action: str,
    source: str,
    ok: bool,
    status: Optional[str] = None,
    finished_at: str = "2026-01-01T00:00:00+00:00",
):
    return {
        "action": action,
        "source": source,
        "ok": ok,
        "status": status or ("ok" if ok else "error"),
        "finished_at": finished_at,
    }


def test_template_summary_on_empty_history():
    assert summary.build_template_summary([]) == "Todavía no se ha registrado ninguna ejecución."


def test_template_summary_reports_counts_and_latest_run():
    entries = [
        _entry("extract_bc", "admin", ok=True),
        _entry("sync_factorial", "admin", ok=False),
    ]

    text = summary.build_template_summary(entries)

    assert "1 correcta" in text
    assert "1 con error" in text
    assert "extract_bc" not in text  # must use the human label, not the raw action key
    assert "BC · Extraer" in text


def test_template_summary_includes_stopped_count_only_when_present():
    entries = [_entry("extract_bc", "admin", ok=True)]
    assert "detenida" not in summary.build_template_summary(entries)

    entries_with_stop = [_entry("extract_bc", "admin", ok=False, status="stopped")]
    assert "detenida" in summary.build_template_summary(entries_with_stop)


def test_template_summary_includes_elevated_error_rate_alerts():
    entries = [_entry("sync_bc", "admin", ok=False)] * 3 + [_entry("sync_bc", "admin", ok=True)] * 2

    text = summary.build_template_summary(entries)

    assert "Aviso" in text
    assert "tasa de error elevada" in text


def test_build_summary_uses_template_when_llm_not_requested():
    entries = [_entry("extract_bc", "admin", ok=True)]

    text, mode = summary.build_summary(entries, use_llm=False)

    assert mode == "template"
    assert text == summary.build_template_summary(entries)


def test_build_summary_falls_back_to_template_when_llm_not_configured(monkeypatch):
    monkeypatch.delenv("TAIDY_SUMMARY_PROVIDER", raising=False)
    entries = [_entry("extract_bc", "admin", ok=True)]

    text, mode = summary.build_summary(entries, use_llm=True)

    assert mode == "template"
    assert text == summary.build_template_summary(entries)


def test_build_summary_falls_back_to_template_when_the_llm_call_fails(monkeypatch):
    def _always_fails(prompt, env=None):
        raise llm_providers.LlmError("simulated failure")

    monkeypatch.setattr(llm_providers, "generate_narrative_summary", _always_fails)
    entries = [_entry("extract_bc", "admin", ok=True)]

    text, mode = summary.build_summary(entries, use_llm=True)

    assert mode == "template"


def test_build_summary_uses_the_llm_when_it_succeeds(monkeypatch):
    monkeypatch.setattr(llm_providers, "generate_narrative_summary", lambda prompt, env=None: "resumen de la IA")
    entries = [_entry("extract_bc", "admin", ok=True)]

    text, mode = summary.build_summary(entries, use_llm=True)

    assert mode == "llm"
    assert text == "resumen de la IA"
