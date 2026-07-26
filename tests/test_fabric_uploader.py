# -*- coding: utf-8 -*-
"""
Regression test for a real bug found while investigating a user report:
one file exhausting its upload retries aborted the entire batch, silently
turning a partially-successful upload into a total reported failure and
skipping every file that would have come after it.

FabricUploader.upload_files() must now: keep going after a per-file
failure, return an accurate (uploaded, skipped, failed) tally, and its two
callers (src/fabric_upload/cli.py, src/factorial_client/push.py) must
surface a non-zero exit code when anything failed rather than reporting
success.
"""

from __future__ import annotations

import sys
from pathlib import Path, PurePosixPath

import pytest
from azure.core.exceptions import ResourceNotFoundError

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.fabric_upload.config import FabricUploadSettings  # noqa: E402
from src.fabric_upload.uploader import FabricUploader  # noqa: E402


class _FakeFileClient:
    def __init__(self, name: str, should_fail: bool) -> None:
        self._name = name
        self._should_fail = should_fail

    def get_file_properties(self):
        raise ResourceNotFoundError("not found")

    def upload_data(self, data: bytes, *, overwrite: bool) -> None:
        if self._should_fail:
            raise TimeoutError(f"simulated transient failure for {self._name}")


class _FakeFileSystemClient:
    def __init__(self, failing_names: set[str]) -> None:
        self._failing_names = failing_names

    def get_file_client(self, remote_path: str):
        name = remote_path.rsplit("/", 1)[-1]
        return _FakeFileClient(name, should_fail=name in self._failing_names)

    def create_directory(self, path: str) -> None:
        pass


@pytest.fixture
def settings(tmp_path: Path) -> FabricUploadSettings:
    full_dir = tmp_path / "full"
    full_dir.mkdir()
    for name in ("a", "b", "c"):
        (full_dir / f"{name}.csv").write_text("col1,col2\n1,2\n", encoding="utf-8")
    return FabricUploadSettings(
        tenant_id="t",
        client_id="c",
        client_secret="s",
        workspace_name="ws",
        lakehouse_name="lh",
        workspace_id=None,
        lakehouse_id=None,
        remote_base=PurePosixPath("raw/test"),
        checkpoint_root=PurePosixPath("raw/checkpoints/test"),
        local_export_root=full_dir,
        overwrite=True,
        max_retries=1,
    )


def test_one_failing_file_does_not_abort_the_rest(settings: FabricUploadSettings):
    fake_fs = _FakeFileSystemClient(failing_names={"b.csv"})
    uploader = FabricUploader(settings, file_system_client=fake_fs, sleep_fn=lambda _: None)

    files = uploader.discover_csv_files()
    assert len(files) == 3

    uploaded, skipped, failed = uploader.upload_files(files)

    assert failed == 1
    assert uploaded == 2
    assert skipped == 0


def test_no_failures_reports_zero_failed(settings: FabricUploadSettings):
    fake_fs = _FakeFileSystemClient(failing_names=set())
    uploader = FabricUploader(settings, file_system_client=fake_fs, sleep_fn=lambda _: None)

    uploaded, skipped, failed = uploader.upload_files(uploader.discover_csv_files())

    assert (uploaded, skipped, failed) == (3, 0, 0)
