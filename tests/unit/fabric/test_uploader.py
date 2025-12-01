from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import List

from src.fabric_upload.uploader import (
    FabricUploader,
    ServiceRequestError,
)
from .helpers import (
    _write_incremental_file,
    _write_full_file,
    _settings,
    DummyFileClient,
    RecordingFileSystem,
    _http_error,
)
import pytest
from src.fabric_upload.uploader import (
    HttpResponseError,
)


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
