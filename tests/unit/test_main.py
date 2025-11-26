from pathlib import Path

import pytest

from src import main
from src.bc_client.config import Settings, TableConfig


class DummyClient:
    def __init__(self, rows_by_url: dict[str, list[dict[str, object]]]) -> None:
        self._rows_by_url = rows_by_url
        self.called_urls: list[str] = []

    def get_table_rows(
        self, table_url: str, *, label: str | None = None
    ) -> list[dict[str, object]]:
        self.called_urls.append(table_url)
        return self._rows_by_url.get(table_url, [])


class DummyTokenProvider:
    def __init__(self, *_, **__) -> None:
        self.called = True

    def get_access_token(self) -> str:  # pragma: no cover - unused in test
        return "token"


class RecordingClient(DummyClient):
    created: list["RecordingClient"] = []

    def __init__(self, rows_by_url: dict[str, list[dict[str, object]]]) -> None:
        super().__init__(rows_by_url)
        self.__class__.created.append(self)


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
    client = DummyClient(
        {
            "https://example.com/customers": [{"id": 1}],
            "https://example.com/vendors": [{"id": 2}],
        }
    )
    exported: list[tuple[str, list[dict[str, object]]]] = []

    monkeypatch.setattr(main, "load_dotenv", lambda *_, **__: True)
    monkeypatch.setattr(main, "load_settings", lambda: settings)
    monkeypatch.setattr(
        main, "OAuthTokenProvider", lambda **kwargs: DummyTokenProvider()
    )
    monkeypatch.setattr(main, "BusinessCentralClient", lambda **kwargs: client)

    def fake_export(table_name, rows, output_dir):
        exported.append((table_name, list(rows)))
        return output_dir / f"{table_name}.csv"

    monkeypatch.setattr(main, "export_table", fake_export)

    exit_code = main.run([])

    assert exit_code == 0
    assert exported == [
        ("customers", [{"id": 1}]),
        ("vendors", [{"id": 2}]),
    ]


def test_run_tables_override_filters_targets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = _settings(tmp_path)
    client = DummyClient(
        {
            "https://example.com/customers": [{"id": 1}],
            "https://example.com/vendors": [{"id": 2}],
        }
    )

    monkeypatch.setattr(main, "load_dotenv", lambda *_, **__: True)
    monkeypatch.setattr(main, "load_settings", lambda: settings)
    monkeypatch.setattr(
        main, "OAuthTokenProvider", lambda **kwargs: DummyTokenProvider()
    )
    monkeypatch.setattr(main, "BusinessCentralClient", lambda **kwargs: client)

    exported: list[str] = []

    def fake_export(table_name, rows, output_dir):
        exported.append(table_name)
        return output_dir / f"{table_name}.csv"

    monkeypatch.setattr(main, "export_table", fake_export)

    exit_code = main.run(["--tables", "customers"])

    assert exit_code == 0
    assert exported == ["customers"]


def test_run_unknown_table_returns_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = _settings(tmp_path)

    monkeypatch.setattr(main, "load_dotenv", lambda *_, **__: True)
    monkeypatch.setattr(main, "load_settings", lambda: settings)
    monkeypatch.setattr(
        main, "OAuthTokenProvider", lambda **kwargs: DummyTokenProvider()
    )
    monkeypatch.setattr(main, "BusinessCentralClient", lambda **kwargs: DummyClient({}))
    monkeypatch.setattr(main, "export_table", lambda *_, **__: None)

    exit_code = main.run(["--tables", "missing"])

    assert exit_code == 1


def test_run_respects_dry_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    monkeypatch.setattr(main, "load_dotenv", lambda *_, **__: True)
    monkeypatch.setattr(main, "load_settings", lambda: settings)
    monkeypatch.setattr(
        main, "OAuthTokenProvider", lambda **kwargs: DummyTokenProvider()
    )
    monkeypatch.setattr(main, "BusinessCentralClient", lambda **kwargs: DummyClient({}))

    called = []

    def fake_export(table_name, rows, output_dir):
        called.append(table_name)
        return output_dir / f"{table_name}.csv"

    monkeypatch.setattr(main, "export_table", fake_export)

    exit_code = main.run(["--dry-run"])

    assert exit_code == 0
    assert called == []


def test_run_returns_failure_on_exception(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = _settings(tmp_path)

    monkeypatch.setattr(main, "load_dotenv", lambda *_, **__: True)
    monkeypatch.setattr(main, "load_settings", lambda: settings)

    def fail_export(*_, **__):
        raise RuntimeError("boom")

    monkeypatch.setattr(main, "export_table", fail_export)
    monkeypatch.setattr(
        main, "OAuthTokenProvider", lambda **kwargs: DummyTokenProvider()
    )
    monkeypatch.setattr(main, "BusinessCentralClient", lambda **kwargs: DummyClient({}))

    exit_code = main.run([])

    assert exit_code == 1


def test_run_supports_parallel_exports(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = _settings(tmp_path)
    rows = {
        "https://example.com/customers": [{"id": 1}],
        "https://example.com/vendors": [{"id": 2}],
    }
    RecordingClient.created.clear()

    monkeypatch.setattr(main, "load_dotenv", lambda *_, **__: True)
    monkeypatch.setattr(main, "load_settings", lambda: settings)
    monkeypatch.setattr(
        main, "OAuthTokenProvider", lambda **kwargs: DummyTokenProvider()
    )
    monkeypatch.setattr(
        main, "BusinessCentralClient", lambda **kwargs: RecordingClient(rows)
    )

    exported: list[str] = []

    def fake_export(table_name, rows_iter, output_dir):
        exported.append(table_name)
        list(rows_iter)
        return output_dir / f"{table_name}.csv"

    monkeypatch.setattr(main, "export_table", fake_export)

    exit_code = main.run(["--parallel", "2"])

    assert exit_code == 0
    assert sorted(exported) == ["customers", "vendors"]
    assert len(RecordingClient.created) == 2
