from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.fabric_upload.checkpoints import FabricCheckpointStore
from .helpers import (
    _settings,
    DummyFileClient,
    RecordingFileSystem,
)


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
