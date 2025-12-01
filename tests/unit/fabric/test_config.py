from __future__ import annotations

from pathlib import Path

import pytest

from src.fabric_upload.config import load_fabric_settings
from src.fabric_upload.client_factory import _account_url
from .helpers import (
    _base_fabric_config,
    _secret_env,
    _settings,
)


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
    monkeypatch.delenv("FABRIC_CLIENT_SECRET", raising=False)

    with pytest.raises(ValueError) as exc:
        load_fabric_settings(
            tmp_path,
            config_data=config,
            config_dir=tmp_path,
        )

    assert "Missing required Fabric upload configuration" in str(exc.value)


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
