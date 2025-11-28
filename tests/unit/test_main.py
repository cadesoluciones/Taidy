from datetime import datetime, timezone
from pathlib import Path

import pytest

from src import main
from src.bc_client.config import Settings, TableConfig
from src.ingest.jobs import compute_new_watermark, prepare_export_jobs


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


def _mock_default_env(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> None:
    monkeypatch.setattr(main, "load_dotenv", lambda *_, **__: True)
    monkeypatch.setattr(main, "load_settings", lambda: settings)
    monkeypatch.setattr(main, "build_checkpoint_store", lambda *_, **__: None)
    monkeypatch.setattr(
        main,
        "_resolve_run_output_dir",
        lambda base, mode, now=None: base / f"{mode}_dir",
    )


def test_run_triggers_exports(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _mock_default_env(monkeypatch, settings)

    jobs = ["job1"]
    captured: dict[str, object] = {}

    def fake_prepare(tables, store, mode):
        captured["tables"] = tables
        captured["mode"] = mode
        return jobs

    monkeypatch.setattr(main, "prepare_export_jobs", fake_prepare)

    def fake_run_exports(jobs_arg, settings_arg, store_arg, workers_arg):
        captured["jobs"] = jobs_arg
        captured["workers"] = workers_arg
        captured["output_dir"] = settings_arg.output_dir
        return len(jobs_arg), 0

    monkeypatch.setattr(main, "run_exports", fake_run_exports)

    exit_code, _ = main.run_extract([])

    assert exit_code == 0
    assert captured["jobs"] == jobs
    assert captured["workers"] == 1
    assert captured["mode"] == "incremental"
    assert str(captured["output_dir"].as_posix()).endswith("incremental_dir")
    assert captured["output_dir"].exists()


def test_run_tables_override_filters_targets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = _settings(tmp_path)
    _mock_default_env(monkeypatch, settings)

    captured: dict[str, object] = {}

    def fake_prepare(tables, store, mode):
        captured["names"] = [table.name for table in tables]
        return []

    monkeypatch.setattr(main, "prepare_export_jobs", fake_prepare)
    monkeypatch.setattr(main, "run_exports", lambda *_, **__: (0, 0))

    exit_code, _ = main.run_extract(["--tables", "customers"])

    assert exit_code == 0
    assert captured["names"] == ["customers"]


def test_run_unknown_table_returns_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = _settings(tmp_path)

    _mock_default_env(monkeypatch, settings)
    monkeypatch.setattr(main, "prepare_export_jobs", lambda *_, **__: [])
    monkeypatch.setattr(main, "run_exports", lambda *_, **__: (0, 0))

    exit_code, _ = main.run_extract(["--tables", "missing"])

    assert exit_code == 1


def test_run_respects_dry_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    _mock_default_env(monkeypatch, settings)
    monkeypatch.setattr(main, "prepare_export_jobs", lambda *_, **__: ["job"])
    called = {"dry_run": False}

    def fake_log(jobs, output_dir):
        called["dry_run"] = True

    monkeypatch.setattr(main, "log_dry_run", fake_log)
    monkeypatch.setattr(
        main,
        "run_exports",
        lambda *_, **__: (_ for _ in ()).throw(AssertionError("should not run")),
    )

    exit_code, _ = main.run_extract(["--dry-run"])

    assert exit_code == 0
    assert called["dry_run"] is True


def test_run_returns_failure_on_exception(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = _settings(tmp_path)

    _mock_default_env(monkeypatch, settings)

    def fail_prepare(*_, **__):
        raise RuntimeError("boom")

    monkeypatch.setattr(main, "prepare_export_jobs", fail_prepare)

    exit_code, _ = main.run_extract([])

    assert exit_code == 1


def test_run_supports_parallel_exports(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = _settings(tmp_path)
    _mock_default_env(monkeypatch, settings)
    monkeypatch.setattr(main, "prepare_export_jobs", lambda *_, **__: ["job"])

    def fake_run_exports(jobs, _settings, store, workers):
        return len(jobs), 0

    monkeypatch.setattr(main, "run_exports", fake_run_exports)

    exit_code, output_dir = main.run_extract(["--parallel", "2"])

    assert exit_code == 0
    assert str(output_dir.as_posix()).endswith("incremental_dir")


def test_run_full_mode_uses_full_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = _settings(tmp_path)
    _mock_default_env(monkeypatch, settings)
    monkeypatch.setattr(main, "prepare_export_jobs", lambda *_, **__: ["job"])

    captured = {}

    def fake_run_exports(jobs, updated_settings, store, workers):
        captured["output_dir"] = updated_settings.output_dir
        return len(jobs), 0

    monkeypatch.setattr(main, "run_exports", fake_run_exports)

    exit_code, _ = main.run_extract(["--mode", "full"])

    assert exit_code == 0
    assert str(captured["output_dir"].as_posix()).endswith("full_dir")


def test_resolve_run_output_dir_incremental_uses_timestamp(tmp_path: Path) -> None:
    base = tmp_path / "exports"
    now = datetime(2024, 5, 1, 12, 34, 56, tzinfo=timezone.utc)

    result = main._resolve_run_output_dir(base, "incremental", now=now)

    assert result == base / "incremental" / "20240501T123456Z"


def test_resolve_run_output_dir_full(tmp_path: Path) -> None:
    base = tmp_path / "exports"

    result = main._resolve_run_output_dir(base, "full")

    assert result == base / "full"


def test_prepare_export_jobs_adds_filter() -> None:
    table = TableConfig(
        name="customers",
        url="https://example.com/customers",
        incremental=True,
    )

    class DummyStore:
        def load(self, table_name: str):
            assert table_name == "customers"
            return type("Checkpoint", (), {"watermark_value": "2024-01-01T00:00:00Z"})()

    jobs = prepare_export_jobs([table], DummyStore(), mode="incremental")

    assert len(jobs) == 1
    assert "%24filter" in jobs[0].request_url
    assert "SystemModifiedAt+gt+2024-01-01T00%3A00%3A00Z" in jobs[0].request_url


def test_prepare_export_jobs_full_mode_omits_filter() -> None:
    table = TableConfig(
        name="customers",
        url="https://example.com/customers",
        incremental=True,
    )

    class DummyStore:
        def load(self, table_name: str):
            return type("Checkpoint", (), {"watermark_value": "2024-01-01T00:00:00Z"})()

    jobs = prepare_export_jobs([table], DummyStore(), mode="full")

    assert len(jobs) == 1
    assert "%24filter" not in jobs[0].request_url
    assert "%24orderby=SystemModifiedAt+asc" in jobs[0].request_url


def test_compute_new_watermark_uses_system_modified_at() -> None:
    rows = [
        {"SystemModifiedAt": "2024-05-01T10:00:00Z"},
        {"SystemModifiedAt": "2024-05-01T11:00:00Z"},
        {"SystemModifiedAt": "2024-05-02T01:00:00Z"},
    ]

    result = compute_new_watermark(rows)

    assert result == "2024-05-02T01:00:00Z"
