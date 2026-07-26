# -*- coding: utf-8 -*-
"""
webapp/llm_providers.py is strictly opt-in (webapp/summary.py always has a
working template fallback) -- these tests mock requests.post so no test run
ever makes a real network call to Anthropic/OpenAI/Gemini, and prove: each
provider is only attempted when its API key is actually set, a non-200
response or malformed body raises LlmError (never lets a bad response
silently produce garbage text), and an unconfigured/unknown provider name
raises rather than picking one arbitrarily.
"""

from __future__ import annotations

import requests

from webapp import llm_providers


class _FakeResponse:
    def __init__(self, status_code, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text

    def json(self):
        return self._json_data


def test_active_provider_is_none_when_unset():
    assert llm_providers.active_provider({}) is None


def test_active_provider_is_none_for_an_unknown_name():
    assert llm_providers.active_provider({"TAIDY_SUMMARY_PROVIDER": "not-a-real-provider"}) is None


def test_active_provider_recognizes_each_supported_name():
    for name in ("anthropic", "openai", "gemini"):
        assert llm_providers.active_provider({"TAIDY_SUMMARY_PROVIDER": name}) == name


def test_generate_narrative_summary_raises_when_no_provider_configured():
    try:
        llm_providers.generate_narrative_summary("hola", {})
        assert False, "expected LlmError"
    except llm_providers.LlmError:
        pass


def test_anthropic_raises_when_api_key_missing():
    env = {"TAIDY_SUMMARY_PROVIDER": "anthropic"}
    try:
        llm_providers.generate_narrative_summary("hola", env)
        assert False, "expected LlmError"
    except llm_providers.LlmError as exc:
        assert "ANTHROPIC_API_KEY" in str(exc)


def test_anthropic_returns_the_generated_text(monkeypatch):
    monkeypatch.setattr(
        requests,
        "post",
        lambda *a, **k: _FakeResponse(200, json_data={"content": [{"text": " resumen generado "}]}),
    )
    env = {"TAIDY_SUMMARY_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "key"}

    assert llm_providers.generate_narrative_summary("hola", env) == "resumen generado"


def test_anthropic_raises_on_non_200(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: _FakeResponse(401, text="unauthorized"))
    env = {"TAIDY_SUMMARY_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "bad-key"}

    try:
        llm_providers.generate_narrative_summary("hola", env)
        assert False, "expected LlmError"
    except llm_providers.LlmError as exc:
        assert "401" in str(exc)


def test_anthropic_raises_on_malformed_response_body(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: _FakeResponse(200, json_data={"unexpected": "shape"}))
    env = {"TAIDY_SUMMARY_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "key"}

    try:
        llm_providers.generate_narrative_summary("hola", env)
        assert False, "expected LlmError"
    except llm_providers.LlmError:
        pass


def test_openai_returns_the_generated_text(monkeypatch):
    monkeypatch.setattr(
        requests,
        "post",
        lambda *a, **k: _FakeResponse(200, json_data={"choices": [{"message": {"content": "resumen"}}]}),
    )
    env = {"TAIDY_SUMMARY_PROVIDER": "openai", "OPENAI_API_KEY": "key"}

    assert llm_providers.generate_narrative_summary("hola", env) == "resumen"


def test_openai_base_url_override_reaches_a_local_model_server(monkeypatch):
    captured_url = {}

    def _fake_post(url, **kwargs):
        captured_url["value"] = url
        return _FakeResponse(200, json_data={"choices": [{"message": {"content": "resumen local"}}]})

    monkeypatch.setattr(requests, "post", _fake_post)
    env = {
        "TAIDY_SUMMARY_PROVIDER": "openai",
        "OPENAI_API_KEY": "unused-by-local-servers-but-required-here",
        "OPENAI_BASE_URL": "http://localhost:11434/v1",
    }

    result = llm_providers.generate_narrative_summary("hola", env)

    assert result == "resumen local"
    assert captured_url["value"] == "http://localhost:11434/v1/chat/completions"


def test_gemini_returns_the_generated_text(monkeypatch):
    monkeypatch.setattr(
        requests,
        "post",
        lambda *a, **k: _FakeResponse(
            200, json_data={"candidates": [{"content": {"parts": [{"text": "resumen"}]}}]}
        ),
    )
    env = {"TAIDY_SUMMARY_PROVIDER": "gemini", "GEMINI_API_KEY": "key"}

    assert llm_providers.generate_narrative_summary("hola", env) == "resumen"


def test_network_error_raises_llm_error_not_the_underlying_exception(monkeypatch):
    def _raise(*a, **k):
        raise requests.ConnectionError("dropped")

    monkeypatch.setattr(requests, "post", _raise)
    env = {"TAIDY_SUMMARY_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "key"}

    try:
        llm_providers.generate_narrative_summary("hola", env)
        assert False, "expected LlmError"
    except llm_providers.LlmError:
        pass
