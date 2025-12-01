from pathlib import Path
from types import SimpleNamespace

import pytest

from src.bc_client.config import TableConfig
from src.ingest import checkpoints


def _table(name: str, *, incremental: bool) -> TableConfig:
    return TableConfig(
        name=name,
        url=f"https://example.com/{name}",
        incremental=incremental,
    )


def test_build_checkpoint_store_returns_none_when_no_incremental(
    tmp_path: Path,
) -> None:
    tables = [_table("customers", incremental=False)]

    store = checkpoints.build_checkpoint_store(tables, tmp_path)

    assert store is None


def test_build_checkpoint_store_creates_store(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    tables = [_table("customers", incremental=True)]
    captured = {}

    def fake_load(output_dir, *, force_enable, checkpoint_path_override):
        captured["output_dir"] = output_dir
        captured["force_enable"] = force_enable
        captured["checkpoint_override"] = checkpoint_path_override
        return SimpleNamespace()

    monkeypatch.setattr(checkpoints, "load_fabric_settings", fake_load)

    class DummyStore:
        def __init__(self, settings) -> None:
            self.settings = settings

    monkeypatch.setattr(checkpoints, "FabricCheckpointStore", DummyStore)

    result = checkpoints.build_checkpoint_store(
        tables, tmp_path, checkpoint_path_override="raw/alt"
    )

    assert isinstance(result, DummyStore)
    assert captured["output_dir"] == tmp_path
    assert captured["force_enable"] is True
    assert captured["checkpoint_override"] == "raw/alt"


def test_build_checkpoint_store_raises_when_settings_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    tables = [_table("customers", incremental=True)]
    monkeypatch.setattr(checkpoints, "load_fabric_settings", lambda *_, **__: None)

    with pytest.raises(RuntimeError):
        checkpoints.build_checkpoint_store(tables, tmp_path)


def test_reset_checkpoints_deletes_only_incremental(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    class DummyStore:
        def delete(self, name: str) -> None:
            calls.append(name)

    tables = [
        _table("customers", incremental=True),
        _table("vendors", incremental=False),
        _table("items", incremental=True),
    ]

    checkpoints.reset_checkpoints(DummyStore(), tables)

    assert calls == ["customers", "items"]
