from pathlib import Path

import pytest

from src.cli import sync


def test_sync_runs_extract_then_upload(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[str] = []

    def fake_run_extract(argv):
        calls.append("extract")
        return 0, tmp_path

    def fake_upload(argv):
        calls.append("upload")
        assert argv == ["--output-dir", str(tmp_path)]
        return 0

    monkeypatch.setattr(sync, "run_extract", fake_run_extract)
    monkeypatch.setattr(sync.fabric_cli, "run", fake_upload)

    exit_code = sync.run([])

    assert exit_code == 0
    assert calls == ["extract", "upload"]


def test_sync_fails_when_extract_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sync, "run_extract", lambda argv: (1, None))

    exit_code = sync.run([])

    assert exit_code == 1
