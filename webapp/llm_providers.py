# -*- coding: utf-8 -*-
"""
Optional LLM backend for webapp/summary.py's "resumen de actividad" --
strictly opt-in. Nothing here is ever called unless TAIDY_SUMMARY_PROVIDER
is set, and the template summary (webapp/summary.build_template_summary)
always works with zero configuration and zero external calls.

Three providers, picked by TAIDY_SUMMARY_PROVIDER:
  "anthropic" -- ANTHROPIC_API_KEY (+ optional ANTHROPIC_MODEL)
  "openai"    -- OPENAI_API_KEY (+ optional OPENAI_MODEL, OPENAI_BASE_URL)
                 OPENAI_BASE_URL lets this same path reach any
                 OpenAI-API-compatible server, including a locally-hosted
                 model (Ollama, LM Studio, vLLM, ...) instead of OpenAI itself.
  "gemini"    -- GEMINI_API_KEY (+ optional GEMINI_MODEL)

All three are plain HTTPS calls via `requests` -- no vendor SDK added as a
dependency for what is, here, a single request/response call.
"""

from __future__ import annotations

import os
from typing import Optional

import requests

_TIMEOUT_SECONDS = 30
_MAX_TOKENS = 300


class LlmError(RuntimeError):
    """Raised for any reason the LLM path can't produce a summary right now
    (not configured, bad credentials, network error, unexpected response) --
    webapp/summary.build_summary() catches this and falls back to the
    template summary rather than ever failing the dashboard."""


def _generate_with_anthropic(prompt: str, env: dict) -> str:
    api_key = env.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise LlmError("ANTHROPIC_API_KEY no está configurada.")
    model = env.get("ANTHROPIC_MODEL", "claude-3-5-haiku-latest")

    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={"model": model, "max_tokens": _MAX_TOKENS, "messages": [{"role": "user", "content": prompt}]},
            timeout=_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise LlmError(f"No se pudo contactar con Anthropic: {exc}") from exc

    if response.status_code != 200:
        raise LlmError(f"Anthropic devolvió un error (HTTP {response.status_code}): {response.text}")
    try:
        return response.json()["content"][0]["text"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise LlmError(f"Respuesta de Anthropic con formato inesperado: {exc}") from exc


def _generate_with_openai(prompt: str, env: dict) -> str:
    api_key = env.get("OPENAI_API_KEY")
    if not api_key:
        raise LlmError("OPENAI_API_KEY no está configurada.")
    model = env.get("OPENAI_MODEL", "gpt-4o-mini")
    base_url = env.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")

    try:
        response = requests.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": _MAX_TOKENS,
            },
            timeout=_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise LlmError(f"No se pudo contactar con el servidor OpenAI-compatible ({base_url}): {exc}") from exc

    if response.status_code != 200:
        raise LlmError(f"El servidor OpenAI-compatible devolvió un error (HTTP {response.status_code}): {response.text}")
    try:
        return response.json()["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise LlmError(f"Respuesta con formato inesperado ({base_url}): {exc}") from exc


def _generate_with_gemini(prompt: str, env: dict) -> str:
    api_key = env.get("GEMINI_API_KEY")
    if not api_key:
        raise LlmError("GEMINI_API_KEY no está configurada.")
    model = env.get("GEMINI_MODEL", "gemini-1.5-flash")

    try:
        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            params={"key": api_key},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": _MAX_TOKENS},
            },
            timeout=_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise LlmError(f"No se pudo contactar con Gemini: {exc}") from exc

    if response.status_code != 200:
        raise LlmError(f"Gemini devolvió un error (HTTP {response.status_code}): {response.text}")
    try:
        return response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise LlmError(f"Respuesta de Gemini con formato inesperado: {exc}") from exc


_PROVIDERS = {
    "anthropic": _generate_with_anthropic,
    "openai": _generate_with_openai,
    "gemini": _generate_with_gemini,
}


def active_provider(env: Optional[dict] = None) -> Optional[str]:
    """The configured provider name, or None if summaries are template-only."""
    raw_env = env if env is not None else os.environ
    provider = raw_env.get("TAIDY_SUMMARY_PROVIDER", "").strip().lower()
    return provider if provider in _PROVIDERS else None


def generate_narrative_summary(prompt: str, env: Optional[dict] = None) -> str:
    raw_env = env if env is not None else os.environ
    provider = active_provider(raw_env)
    if provider is None:
        raise LlmError("No hay ningún proveedor de IA configurado (TAIDY_SUMMARY_PROVIDER).")
    return _PROVIDERS[provider](prompt, raw_env)
