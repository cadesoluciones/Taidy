# -*- coding: utf-8 -*-
"""
FabricCheckpointStore (src/fabric_upload/checkpoints.py) is the single source
of truth for every incremental BC/Factorial watermark -- both src/ingest/ and
src/factorial_client/ read/write through it via Fabric OneLake. Despite that
central role it had zero test coverage; only src/factorial_client/checkpoints.py
(the separate, purely-local checkpoint store) was ever exercised.

These tests use a fake file-system client (same style as
tests/test_fabric_uploader.py's _FakeFileSystemClient) instead of talking to
real OneLake, covering: the missing-checkpoint case, a corrupted JSON payload,
the 'Z'-suffixed timestamp format Fabric actually returns, and delete being a
no-op when nothing was ever saved.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

import pytest
from azure.core.exceptions import HttpResponseError, ResourceNotFoundError

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.fabric_upload.checkpoints import FabricCheckpointStore  # noqa: E402
from src.fabric_upload.config import FabricUploadSettings  # noqa: E402


class _Downloaded:
    def __init__(self, data: bytes):
        self._data = data

    def readall(self) -> bytes:
        return self._data


class _FakeFileClient:
    def __init__(self, store: dict, path: str):
        self._store = store
        self._path = path

    def download_file(self) -> _Downloaded:
        if self._path not in self._store:
            raise ResourceNotFoundError("not found")
        return _Downloaded(self._store[self._path])

    def upload_data(self, data: bytes, *, overwrite: bool) -> None:
        self._store[self._path] = data

    def delete_file(self) -> None:
        if self._path not in self._store:
            raise ResourceNotFoundError("not found")
        del self._store[self._path]


class _FakeFileSystemClient:
    def __init__(self):
        self._store: dict = {}
        self.created_dirs: list[str] = []

    def get_file_client(self, path: str) -> _FakeFileClient:
        return _FakeFileClient(self._store, path)

    def create_directory(self, path: str) -> None:
        self.created_dirs.append(path)


class _ErroringFileClient:
    def download_file(self):
        raise HttpResponseError("service unavailable")


@pytest.fixture
def settings(tmp_path: Path) -> FabricUploadSettings:
    return FabricUploadSettings(
        tenant_id="t",
        client_id="c",
        client_secret="s",
        workspace_name="ws",
        lakehouse_name="lh",
        workspace_id=None,
        lakehouse_id=None,
        remote_base=PurePosixPath("raw/business_central"),
        checkpoint_root=PurePosixPath("raw/checkpoints/business_central"),
        local_export_root=tmp_path,
        overwrite=True,
        max_retries=3,
    )


def test_load_with_no_checkpoint_returns_none(settings):
    store = FabricCheckpointStore(settings, file_system_client=_FakeFileSystemClient())

    assert store.load("employees") is None


def test_save_then_load_roundtrips_watermark(settings):
    fixed_now = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
    store = FabricCheckpointStore(
        settings, file_system_client=_FakeFileSystemClient(), now_fn=lambda: fixed_now
    )

    saved = store.save("employees", "2026-03-15T00:00:00Z", watermark_column="SystemModifiedAt")
    assert saved.watermark_value == "2026-03-15T00:00:00Z"
    assert saved.updated_at == fixed_now

    loaded = store.load("employees")
    assert loaded.table_name == "employees"
    assert loaded.watermark_value == "2026-03-15T00:00:00Z"
    assert loaded.updated_at == fixed_now


def test_save_ensures_parent_directory_is_created(settings):
    fake_fs = _FakeFileSystemClient()
    store = FabricCheckpointStore(settings, file_system_client=fake_fs)

    store.save("employees", "watermark-1")

    assert fake_fs.created_dirs == ["raw/checkpoints/business_central"]


def test_load_parses_z_suffixed_timestamp(settings):
    fake_fs = _FakeFileSystemClient()
    store = FabricCheckpointStore(settings, file_system_client=fake_fs)
    path = store._remote_path("employees").as_posix()
    fake_fs._store[path] = b'{"watermark_value": "abc", "updated_at": "2026-03-15T10:30:00Z"}'

    loaded = store.load("employees")

    assert loaded.updated_at == datetime(2026, 3, 15, 10, 30, 0, tzinfo=timezone.utc)


def test_load_with_corrupted_json_raises_value_error(settings):
    fake_fs = _FakeFileSystemClient()
    store = FabricCheckpointStore(settings, file_system_client=fake_fs)
    path = store._remote_path("employees").as_posix()
    fake_fs._store[path] = b"not valid json"

    with pytest.raises(ValueError, match="Invalid JSON"):
        store.load("employees")


def test_load_with_missing_updated_at_defaults_to_epoch(settings):
    fake_fs = _FakeFileSystemClient()
    store = FabricCheckpointStore(settings, file_system_client=fake_fs)
    path = store._remote_path("employees").as_posix()
    fake_fs._store[path] = b'{"watermark_value": "abc"}'

    loaded = store.load("employees")

    assert loaded.updated_at == datetime.fromtimestamp(0, tz=timezone.utc)


def test_load_propagates_unexpected_http_errors(settings, monkeypatch):
    store = FabricCheckpointStore(settings, file_system_client=_FakeFileSystemClient())
    monkeypatch.setattr(store._file_system, "get_file_client", lambda path: _ErroringFileClient())

    with pytest.raises(HttpResponseError):
        store.load("employees")


def test_delete_is_a_no_op_when_nothing_was_saved(settings):
    store = FabricCheckpointStore(settings, file_system_client=_FakeFileSystemClient())

    store.delete("employees")  # must not raise


def test_delete_removes_an_existing_checkpoint(settings):
    fake_fs = _FakeFileSystemClient()
    store = FabricCheckpointStore(settings, file_system_client=fake_fs)
    store.save("employees", "watermark-1")

    store.delete("employees")

    assert store.load("employees") is None


def test_remote_path_is_namespaced_per_table(settings):
    store = FabricCheckpointStore(settings, file_system_client=_FakeFileSystemClient())

    assert store._remote_path("employees").as_posix() == "raw/checkpoints/business_central/employees.json"
