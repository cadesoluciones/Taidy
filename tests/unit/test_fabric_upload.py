from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import pytest

from unittest.mock import Mock

from src.fabric_upload.config import FabricUploadSettings, load_fabric_settings
from src.fabric_upload.checkpoints import FabricCheckpointStore
from src.fabric_upload.client_factory import _account_url
from src.fabric_upload import uploader
from src.fabric_upload.uploader import (
    FabricUploader,
    HttpResponseError,
    ResourceNotFoundError,
    ServiceRequestError,
    upload_exports_if_enabled,
)
from src.fabric_upload import cli as fabric_cli


class DummyFileClient:
    def __init__(self) -> None:
        self.exists = False
        self.uploads: List[bytes] = []
        self.overwrite_flags: List[bool] = []
        self.failures: List[Exception] = []
        self.properties_requested = 0
        self.properties_error: Exception | None = None
        self.download_payload: bytes = b""

    def upload_data(self, data: bytes, *, overwrite: bool) -> None:
        if self.failures:
            raise self.failures.pop(0)
        self.uploads.append(data)
        self.overwrite_flags.append(overwrite)
        self.download_payload = data

    def get_file_properties(self) -> dict:
        self.properties_requested += 1
        if self.properties_error is not None:
            error = self.properties_error
            self.properties_error = None
            raise error
        if not self.exists:
            raise ResourceNotFoundError("missing")
        return {}

    def download_file(self):
        return _DownloadResponse(self.download_payload)

    def delete_file(self) -> None:
        self.exists = False


class _DownloadResponse:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def readall(self) -> bytes:
        return self._data


class RecordingFileSystem:
    def __init__(self, client: DummyFileClient | None = None) -> None:
        self.client = client or DummyFileClient()
        self.last_requested_path: str | None = None
        self.created_directories: List[tuple[str, bool]] = []

    def get_file_client(self, file_path: str) -> DummyFileClient:
        self.last_requested_path = file_path
        return self.client

    def create_directory(self, directory: str, *, exist_ok: bool = False) -> None:
        self.created_directories.append((directory, exist_ok))


def _base_fabric_config() -> dict:
    return {
        "fabric_upload": {
            "tenant_id": "tenant",
            "client_id": "client",
            "workspace_name": "Sandbox",
            "lakehouse_name": "Lakehouse",
            "workspace_id": "workspace-guid",
            "lakehouse_id": "lakehouse-guid",
        }
    }


def _secret_env() -> list[tuple[str, str]]:
    return [("FABRIC_CLIENT_SECRET", "secret")]


def _settings(root: Path, **overrides: object) -> FabricUploadSettings:
    base = FabricUploadSettings(
        tenant_id="tenant",
        client_id="client",
        client_secret="secret",
        workspace_name="workspace",
        lakehouse_name="lakehouse",
        workspace_id=None,
        lakehouse_id=None,
        path_prefix="raw",
        source_name="business_central",
        checkpoint_path="raw/checkpoints/business_central",
        overwrite=False,
        max_retries=3,
        local_export_root=root,
    )
    return replace(base, **overrides)


def _write_full_file(root: Path, name: str = "Customers.csv") -> tuple[Path, Path]:
    folder = root / "full"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text("id\n1\n", encoding="utf-8")
    return folder, path


def _write_incremental_file(
    root: Path, run_id: str = "20250102T010203Z", name: str = "Customers.csv"
) -> tuple[Path, Path]:
    folder = root / "incremental" / run_id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text("id\n1\n", encoding="utf-8")
    return folder, path


def test_discover_csv_files_finds_nested_exports(tmp_path: Path) -> None:
    exports = tmp_path / "exports"
    run_folder = exports / "incremental" / "run123"
    nested = run_folder / "nested"
    nested.mkdir(parents=True)
    customer = run_folder / "customers.csv"
    vendor = nested / "vendors.csv"
    customer.write_text("id\n1\n", encoding="utf-8")
    vendor.write_text("id\n2\n", encoding="utf-8")
    (exports / "ignore.txt").write_text("skip", encoding="utf-8")

    uploader_instance = FabricUploader(
        _settings(exports),
        file_system_client=RecordingFileSystem(),
    )

    discovered = uploader_instance.discover_csv_files()

    assert discovered == [customer, vendor]


def test_builds_expected_remote_path_for_incremental(tmp_path: Path) -> None:
    exports = tmp_path / "exports"
    run_id = "20250102T010203Z"
    run_root, file_path = _write_incremental_file(exports, run_id)
    client = DummyFileClient()
    fs = RecordingFileSystem(client)

    def fixed_now() -> datetime:
        return datetime(2025, 1, 2, tzinfo=timezone.utc)

    uploader_instance = FabricUploader(
        _settings(run_root),
        file_system_client=fs,
        now_fn=fixed_now,
    )

    uploader_instance.upload_files([file_path])

    assert (
        fs.last_requested_path
        == f"raw/business_central/incremental/customers/{run_id}/Customers.csv"
    )
    assert client.uploads[0] == file_path.read_bytes()


def test_builds_expected_remote_path_for_full(tmp_path: Path) -> None:
    exports = tmp_path / "exports"
    run_root, file_path = _write_full_file(exports)
    client = DummyFileClient()
    fs = RecordingFileSystem(client)

    uploader_instance = FabricUploader(
        _settings(run_root),
        file_system_client=fs,
    )

    uploader_instance.upload_files([file_path])

    assert fs.last_requested_path == "raw/business_central/full/customers.csv"


def test_load_fabric_settings_disabled_when_flag_missing(tmp_path: Path) -> None:
    config = _base_fabric_config()
    config["fabric_upload"]["enabled"] = False
    result = load_fabric_settings(
        tmp_path,
        config_data=config,
        config_dir=tmp_path,
        env=_secret_env(),
    )

    assert result is None


def test_load_fabric_settings_validates_required(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = _base_fabric_config()

    with pytest.raises(ValueError) as exc:
        load_fabric_settings(
            tmp_path,
            config_data=config,
            config_dir=tmp_path,
        )

    assert "Missing required Fabric upload configuration" in str(exc.value)


def test_upload_skips_when_remote_exists(tmp_path: Path) -> None:
    exports = tmp_path / "exports"
    run_root, file_path = _write_full_file(exports)
    client = DummyFileClient()
    client.exists = True
    fs = RecordingFileSystem(client)

    uploader_instance = FabricUploader(
        _settings(run_root, overwrite=False),
        file_system_client=fs,
    )

    uploader_instance.upload_files([file_path])

    assert client.uploads == []
    assert client.properties_requested == 1


def test_upload_overwrites_when_flag_true(tmp_path: Path) -> None:
    exports = tmp_path / "exports"
    run_root, file_path = _write_full_file(exports)
    client = DummyFileClient()
    client.exists = True
    fs = RecordingFileSystem(client)

    uploader_instance = FabricUploader(
        _settings(run_root, overwrite=True),
        file_system_client=fs,
    )

    uploader_instance.upload_files([file_path])

    assert len(client.uploads) == 1
    assert client.overwrite_flags == [True]


def test_upload_creates_parent_directories(tmp_path: Path) -> None:
    exports = tmp_path / "exports"
    run_id = "20251126T101112Z"
    run_root, file_path = _write_incremental_file(exports, run_id)
    client = DummyFileClient()
    fs = RecordingFileSystem(client)

    uploader_instance = FabricUploader(
        _settings(run_root, overwrite=False),
        file_system_client=fs,
    )

    uploader_instance.upload_files([file_path])

    assert any(
        directory == f"raw/business_central/incremental/customers/{run_id}"
        for directory, _ in fs.created_directories
    )


def test_upload_retries_on_transient_error(tmp_path: Path) -> None:
    exports = tmp_path / "exports"
    run_root, file_path = _write_full_file(exports, name="Vendors.csv")
    client = DummyFileClient()
    client.failures.append(ServiceRequestError("timeout"))
    fs = RecordingFileSystem(client)
    sleeps: List[float] = []

    uploader_instance = FabricUploader(
        _settings(run_root, max_retries=3),
        file_system_client=fs,
        sleep_fn=lambda seconds: sleeps.append(seconds),
    )

    uploader_instance.upload_files([file_path])

    assert len(client.uploads) == 1
    assert sleeps == [1.0]


def test_account_url_uses_onelake_extensions(tmp_path: Path) -> None:
    exports = tmp_path / "exports"
    exports.mkdir()
    settings = _settings(
        exports,
        workspace_name="Sandbox Workspace",
        lakehouse_name="MyLakehouse",
    )

    assert (
        _account_url(settings)
        == "https://onelake.dfs.fabric.microsoft.com/Sandbox%20Workspace/MyLakehouse.Lakehouse"
    )


def test_account_url_prefers_artifact_names(tmp_path: Path) -> None:
    exports = tmp_path / "exports"
    exports.mkdir()
    settings = _settings(
        exports,
        workspace_name="Friendly",
        lakehouse_name="Display",
        workspace_id="44b1286f-484d-41b1-9259-6904105d8d09",
        lakehouse_id="1287f84f-d048-4967-a27f-b3f3019345d9",
    )

    assert (
        _account_url(settings)
        == "https://onelake.dfs.fabric.microsoft.com/Friendly/Display.Lakehouse"
    )


def test_file_exists_treats_http_400_as_missing(tmp_path: Path) -> None:
    exports = tmp_path / "exports"
    exports.mkdir()
    client = DummyFileClient()
    client.properties_error = _http_error(400)
    fs = RecordingFileSystem(client)

    uploader_instance = FabricUploader(_settings(exports), file_system_client=fs)

    assert uploader_instance._file_exists(client) is False


def test_file_exists_re_raises_unexpected_http_errors(tmp_path: Path) -> None:
    exports = tmp_path / "exports"
    exports.mkdir()
    client = DummyFileClient()
    client.properties_error = _http_error(500)
    fs = RecordingFileSystem(client)
    uploader_instance = FabricUploader(_settings(exports), file_system_client=fs)

    with pytest.raises(HttpResponseError):
        uploader_instance._file_exists(client)


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


def _http_error(status_code: int) -> HttpResponseError:
    response = Mock()
    response.status_code = status_code
    response.reason = "error"
    return HttpResponseError(message="error", response=response)


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


def test_checkpoint_store_saves_and_loads(tmp_path: Path) -> None:
    exports = tmp_path / "exports"
    exports.mkdir()
    client = DummyFileClient()
    fs = RecordingFileSystem(client)

    def fixed_now() -> datetime:
        return datetime(2024, 5, 10, tzinfo=timezone.utc)

    store = FabricCheckpointStore(
        _settings(exports, checkpoint_path="raw/checkpoints/bc"),
        file_system_client=fs,
        now_fn=fixed_now,
    )

    store.save(
        "Customers",
        "2024-05-09T12:00:00Z",
        watermark_column="SystemModifiedAt",
    )

    checkpoint = store.load("Customers")

    assert fs.last_requested_path == "raw/checkpoints/bc/customers.json"
    assert checkpoint is not None
    assert checkpoint.watermark_value == "2024-05-09T12:00:00Z"


def test_checkpoint_delete_missing_is_noop(tmp_path: Path) -> None:
    exports = tmp_path / "exports"
    exports.mkdir()
    fs = RecordingFileSystem(DummyFileClient())

    store = FabricCheckpointStore(_settings(exports), file_system_client=fs)

    # Should not raise even if the file does not exist.
    store.delete("Vendors")
