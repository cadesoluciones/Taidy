from __future__ import annotations

import json
from pathlib import Path
from typing import List

import pytest

from src.fabric_upload.config import FabricUploadSettings
from src.fabric_upload import uploader
from src.fabric_upload.uploader import (
    upload_exports_if_enabled,
)
from .helpers import (
    _write_full_file,
    _base_fabric_config,
)


def test_upload_exports_if_enabled_invokes_uploader(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    exports = tmp_path / "exports"
    run_root, file_path = _write_full_file(exports)

    monkeypatch.setenv("FABRIC_UPLOAD_ENABLED", "true")
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
            calls["discover"] = True
            return [file_path]

        def upload_files(self, files: List[Path]) -> tuple[int, int]:
            calls["files"] = list(files)
            return len(files), 0

    monkeypatch.setattr(uploader, "FabricUploader", DummyUploader)

    upload_exports_if_enabled(run_root)

    assert calls["settings"].local_export_root == run_root
    assert calls["discover"] is True
    assert calls["files"] == [file_path]


def test_upload_exports_if_disabled_skips(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("FABRIC_UPLOAD_ENABLED", raising=False)
    monkeypatch.setenv("FABRIC_CLIENT_SECRET", "secret")
    monkeypatch.setenv("CONFIG_FILE", str(tmp_path / "config.json"))
    config = _base_fabric_config()
    config["fabric_upload"]["enabled"] = False
    (tmp_path / "config.json").write_text(
        json.dumps(config),
        encoding="utf-8",
    )
    called = False

    def fail(*_, **__):
        nonlocal called
        called = True

    monkeypatch.setattr(uploader, "FabricUploader", fail)

    upload_exports_if_enabled(tmp_path)

    assert called is False
