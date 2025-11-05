from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

import api_test
from bc_client.config import Settings, TableConfig


class DummyClient:
    def __init__(self, rows_by_url: dict[str, list[dict[str, object]]]) -> None:
        self._rows_by_url = rows_by_url
        self.called_urls: list[str] = []

    def iter_table_rows(self, table_url: str):  # pragma: no cover - generator stub
        self.called_urls.append(table_url)
        for row in self._rows_by_url.get(table_url, []):
            yield row


class DummyTokenProvider:
    def __init__(self, *_, **__) -> None:
        self.called = True

    def get_access_token(self) -> str:  # pragma: no cover - unused in test
        return "token"


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        tenant_id="tenant",
        environment="Sandbox",
        client_id="client",
        client_secret="secret",
        scope="scope",
        token_url="https://example.com/token",
        company_id="00000000-0000-0000-0000-000000000000",
        company_name="Company",
        tables=[
            TableConfig(name="customers", url="https://example.com/customers"),
            TableConfig(name="vendors", url="https://example.com/vendors"),
        ],
        page_size=200,
        output_dir=tmp_path / "exports",
    )


def test_run_triggers_exports(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    client = DummyClient({
        "https://example.com/customers": [{"id": 1}],
        "https://example.com/vendors": [{"id": 2}],
    })
    exported: list[tuple[str, list[dict[str, object]]]] = []

    monkeypatch.setattr(api_test, "load_dotenv", lambda *_, **__: True)
    monkeypatch.setattr(api_test, "load_settings", lambda: settings)
    monkeypatch.setattr(api_test, "OAuthTokenProvider", lambda **kwargs: DummyTokenProvider())
    monkeypatch.setattr(api_test, "BusinessCentralClient", lambda **kwargs: client)

    def fake_export(table_name, rows, output_dir):
        exported.append((table_name, list(rows)))
        return output_dir / f"{table_name}.csv"

    monkeypatch.setattr(api_test, "export_table", fake_export)

    exit_code = api_test.run([])

    assert exit_code == 0
    assert exported == [
        ("customers", [{"id": 1}]),
        ("vendors", [{"id": 2}]),
    ]


def test_run_tables_override_filters_targets(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    client = DummyClient({
        "https://example.com/customers": [{"id": 1}],
        "https://example.com/vendors": [{"id": 2}],
    })

    monkeypatch.setattr(api_test, "load_dotenv", lambda *_, **__: True)
    monkeypatch.setattr(api_test, "load_settings", lambda: settings)
    monkeypatch.setattr(api_test, "OAuthTokenProvider", lambda **kwargs: DummyTokenProvider())
    monkeypatch.setattr(api_test, "BusinessCentralClient", lambda **kwargs: client)

    exported: list[str] = []

    def fake_export(table_name, rows, output_dir):
        exported.append(table_name)
        return output_dir / f"{table_name}.csv"

    monkeypatch.setattr(api_test, "export_table", fake_export)

    exit_code = api_test.run(["--tables", "customers"])

    assert exit_code == 0
    assert exported == ["customers"]


def test_run_unknown_table_returns_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    monkeypatch.setattr(api_test, "load_dotenv", lambda *_, **__: True)
    monkeypatch.setattr(api_test, "load_settings", lambda: settings)
    monkeypatch.setattr(api_test, "OAuthTokenProvider", lambda **kwargs: DummyTokenProvider())
    monkeypatch.setattr(api_test, "BusinessCentralClient", lambda **kwargs: DummyClient({}))
    monkeypatch.setattr(api_test, "export_table", lambda *_, **__: None)

    exit_code = api_test.run(["--tables", "missing"])

    assert exit_code == 1


def test_run_respects_dry_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    monkeypatch.setattr(api_test, "load_dotenv", lambda *_, **__: True)
    monkeypatch.setattr(api_test, "load_settings", lambda: settings)
    monkeypatch.setattr(api_test, "OAuthTokenProvider", lambda **kwargs: DummyTokenProvider())
    monkeypatch.setattr(api_test, "BusinessCentralClient", lambda **kwargs: DummyClient({}))

    called = []

    def fake_export(table_name, rows, output_dir):
        called.append(table_name)
        return output_dir / f"{table_name}.csv"

    monkeypatch.setattr(api_test, "export_table", fake_export)

    exit_code = api_test.run(["--dry-run"])

    assert exit_code == 0
    assert called == []


def test_run_returns_failure_on_exception(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    monkeypatch.setattr(api_test, "load_dotenv", lambda *_, **__: True)
    monkeypatch.setattr(api_test, "load_settings", lambda: settings)

    def fail_export(*_, **__):
        raise RuntimeError("boom")

    monkeypatch.setattr(api_test, "export_table", fail_export)
    monkeypatch.setattr(api_test, "OAuthTokenProvider", lambda **kwargs: DummyTokenProvider())
    monkeypatch.setattr(api_test, "BusinessCentralClient", lambda **kwargs: DummyClient({}))

    exit_code = api_test.run([])

    assert exit_code == 1
