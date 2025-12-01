from __future__ import annotations

from pathlib import Path
from typing import List

import pytest

from src.fabric_upload.config import FabricUploadSettings
from src.fabric_upload import cli as fabric_cli
from .helpers import (
    _write_full_file,
)


def test_cli_uploads_existing_exports(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    exports = tmp_path / "exports"
    run_root, file_path = _write_full_file(exports)

    # Provide the minimal Fabric configuration.
    monkeypatch.setenv("FABRIC_TENANT_ID", "tenant")
    monkeypatch.setenv("FABRIC_CLIENT_ID", "client")
    monkeypatch.setenv("FABRIC_CLIENT_SECRET", "secret")
    monkeypatch.setenv("FABRIC_WORKSPACE_NAME", "workspace")
    monkeypatch.setenv("FABRIC_LAKEHOUSE_NAME", "lake")

    calls: dict[str, object] = {}

    class DummyUploader:
        def __init__(self, settings: FabricUploadSettings) -> None:
            calls["settings"] = settings

        def discover_csv_files(self) -> List[Path]:
            return [file_path]

        def upload_files(self, files: List[Path]) -> tuple[int, int]:
            calls["files"] = list(files)
            return len(files), 0

    monkeypatch.setattr(fabric_cli, "FabricUploader", DummyUploader)

    exit_code = fabric_cli.run(["--output-dir", str(run_root)])

    assert exit_code == 0
    assert calls["settings"].local_export_root == run_root
    assert calls["files"] == [file_path]


def test_cli_dry_run_skips_upload(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    exports = tmp_path / "exports"
    run_root, file_path = _write_full_file(exports)

    monkeypatch.setenv("FABRIC_TENANT_ID", "tenant")
    monkeypatch.setenv("FABRIC_CLIENT_ID", "client")
    monkeypatch.setenv("FABRIC_CLIENT_SECRET", "secret")
    monkeypatch.setenv("FABRIC_WORKSPACE_NAME", "workspace")
    monkeypatch.setenv("FABRIC_LAKEHOUSE_NAME", "lake")

    class DummyUploader:
        def __init__(self, settings: FabricUploadSettings) -> None:
            self.settings = settings

        def discover_csv_files(self) -> List[Path]:
            return [file_path]

        def upload_files(self, files: List[Path]) -> None:
            raise AssertionError("upload_files should not be called in dry-run mode")

    monkeypatch.setattr(fabric_cli, "FabricUploader", DummyUploader)

    exit_code = fabric_cli.run(["--output-dir", str(run_root), "--dry-run"])

    assert exit_code == 0


def test_cli_errors_when_output_dir_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("FABRIC_TENANT_ID", "tenant")
    monkeypatch.setenv("FABRIC_CLIENT_ID", "client")
    monkeypatch.setenv("FABRIC_CLIENT_SECRET", "secret")
    monkeypatch.setenv("FABRIC_WORKSPACE_NAME", "workspace")
    monkeypatch.setenv("FABRIC_LAKEHOUSE_NAME", "lake")

    exit_code = fabric_cli.run(["--output-dir", str(tmp_path / "missing")])

    assert exit_code == 1
