from __future__ import annotations

from dataclasses import replace
from pathlib import Path, PurePosixPath
from typing import List
from unittest.mock import Mock

from src.fabric_upload.config import FabricUploadSettings
from src.fabric_upload.uploader import (
    HttpResponseError,
    ResourceNotFoundError,
)


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
        remote_base=PurePosixPath("raw") / "business_central",
        checkpoint_root=PurePosixPath("raw/checkpoints/business_central"),
        overwrite=False,
        max_retries=3,
        local_export_root=root,
    )
    checkpoint_override = overrides.pop("checkpoint_path", None)
    if checkpoint_override is not None:
        overrides["checkpoint_root"] = PurePosixPath(checkpoint_override)
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


def _http_error(status_code: int) -> HttpResponseError:
    response = Mock()
    response.status_code = status_code
    response.reason = "error"
    return HttpResponseError(message="error", response=response)
