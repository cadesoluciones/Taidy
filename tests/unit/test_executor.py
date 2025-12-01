from pathlib import Path
from types import SimpleNamespace
from typing import List

import pytest

from src.bc_client.config import TableConfig
from src.ingest.executor import (
    _export_single_table,
    _persist_checkpoint,
    run_exports,
)
from src.ingest.jobs import TableExportJob, TableExportResult


class DummyClient:
    def get_table_rows(self, url: str, *, label: str | None = None):
        return []


def test_export_single_table_skips_empty_incremental(tmp_path: Path) -> None:
    table = TableConfig(
        name="customers",
        url="https://example.com/customers",
        incremental=True,
    )
    job = TableExportJob(
        table=table,
        request_url=table.url,
        incremental=True,
    )
    client = DummyClient()

    result = _export_single_table(job, client, tmp_path)

    assert result.new_watermark is None
    assert not (tmp_path / "customers.csv").exists()


def _job(name: str, incremental: bool = True) -> TableExportJob:
    table = TableConfig(
        name=name,
        url=f"https://example.com/{name}",
        incremental=incremental,
    )
    return TableExportJob(table=table, request_url=table.url, incremental=incremental)


def test_run_exports_sequential_reuses_client(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    jobs = [_job("customers"), _job("vendors")]
    sequential_client = object()
    monkeypatch.setattr(
        "src.ingest.executor._create_token_provider", lambda settings: "token"
    )
    client_calls: List[object] = []
    monkeypatch.setattr(
        "src.ingest.executor._create_client",
        lambda settings, token: client_calls.append(sequential_client)
        or sequential_client,
    )

    results = [
        TableExportResult(jobs[0], tmp_path / "customers.csv", "2024-01-01", True),
        TableExportResult(jobs[1], tmp_path / "vendors.csv", None, False),
    ]
    iter_results = iter(results)
    monkeypatch.setattr(
        "src.ingest.executor._export_single_table",
        lambda job, client, output_dir: next(iter_results),
    )
    persisted: List[TableExportResult] = []
    monkeypatch.setattr(
        "src.ingest.executor._persist_checkpoint",
        lambda result, store: persisted.append(result),
    )

    settings = SimpleNamespace(output_dir=tmp_path)

    processed, written = run_exports(jobs, settings, object(), parallel_workers=1)

    assert processed == 2
    assert written == 1
    assert len(client_calls) == 1
    assert persisted == results


def test_run_exports_parallel_uses_worker_per_job(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    jobs = [_job("customers"), _job("vendors")]
    monkeypatch.setattr(
        "src.ingest.executor._create_token_provider", lambda settings: "token"
    )

    created_clients: List[object] = []

    def fake_create_client(settings, token):
        client = object()
        created_clients.append(client)
        return client

    monkeypatch.setattr("src.ingest.executor._create_client", fake_create_client)

    results_map = {
        "customers": TableExportResult(jobs[0], tmp_path / "customers.csv", "w1", True),
        "vendors": TableExportResult(jobs[1], tmp_path / "vendors.csv", None, False),
    }

    def fake_export(job, client, output_dir):
        return results_map[job.table.name]

    monkeypatch.setattr("src.ingest.executor._export_single_table", fake_export)

    persisted: List[TableExportResult] = []
    monkeypatch.setattr(
        "src.ingest.executor._persist_checkpoint",
        lambda result, store: persisted.append(result),
    )

    settings = SimpleNamespace(output_dir=tmp_path)

    processed, written = run_exports(jobs, settings, object(), parallel_workers=2)

    assert processed == 2
    assert written == 1
    assert len(created_clients) == 2
    assert persisted == [results_map["customers"], results_map["vendors"]]


def test_persist_checkpoint_requires_store_for_incremental(tmp_path: Path) -> None:
    result = TableExportResult(
        _job("customers"), tmp_path / "customers.csv", "wm", True
    )
    with pytest.raises(RuntimeError):
        _persist_checkpoint(result, None)


def test_persist_checkpoint_skips_non_incremental(tmp_path: Path) -> None:
    job = _job("customers", incremental=False)
    result = TableExportResult(job, tmp_path / "customers.csv", "wm", True)

    class FailStore:
        def save(self, *args, **kwargs):
            raise AssertionError("should not save")

    _persist_checkpoint(result, FailStore())


def test_persist_checkpoint_saves_when_watermark_present(tmp_path: Path) -> None:
    result = TableExportResult(
        _job("customers"), tmp_path / "customers.csv", "wm", True
    )

    class RecordingStore:
        def __init__(self) -> None:
            self.saved: list[tuple[str, str]] = []

        def save(self, table: str, watermark: str, *, watermark_column: str) -> None:
            self.saved.append((table, watermark, watermark_column))

    store = RecordingStore()

    _persist_checkpoint(result, store)

    assert store.saved == [("customers", "wm", "SystemModifiedAt")]


def test_persist_checkpoint_ignores_missing_watermark(tmp_path: Path) -> None:
    result = TableExportResult(
        _job("customers"), tmp_path / "customers.csv", None, True
    )

    class RecordingStore:
        def __init__(self) -> None:
            self.called = False

        def save(self, *args, **kwargs):
            self.called = True

    store = RecordingStore()

    _persist_checkpoint(result, store)

    assert store.called is False
