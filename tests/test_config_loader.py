# -*- coding: utf-8 -*-
"""
src/config_loader.py resolves config.json's path from three different
sources (explicit arg, CONFIG_FILE env var, default filename) and is
imported by every extraction/upload entry point in src/ -- a silent
regression here (wrong precedence, a swallowed parse error) would be very
hard to notice since every caller just sees "file not found" or similar.
Had zero test coverage until now.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.config_loader import (  # noqa: E402
    DEFAULT_CONFIG_FILE,
    load_config_data,
    resolve_environment,
)


def test_loads_explicit_path(tmp_path: Path):
    config_file = tmp_path / "custom.json"
    config_file.write_text('{"a": 1}', encoding="utf-8")

    data, root = load_config_data(config_file)

    assert data == {"a": 1}
    assert root == tmp_path


def test_explicit_path_argument_wins_over_env_var(tmp_path: Path, monkeypatch):
    explicit = tmp_path / "explicit.json"
    explicit.write_text('{"source": "explicit"}', encoding="utf-8")
    from_env = tmp_path / "from_env.json"
    from_env.write_text('{"source": "env"}', encoding="utf-8")
    monkeypatch.setenv("CONFIG_FILE", str(from_env))

    data, _root = load_config_data(explicit)

    assert data == {"source": "explicit"}


def test_env_var_used_when_no_explicit_path(tmp_path: Path, monkeypatch):
    from_env = tmp_path / "from_env.json"
    from_env.write_text('{"source": "env"}', encoding="utf-8")
    monkeypatch.setenv("CONFIG_FILE", str(from_env))

    data, root = load_config_data()

    assert data == {"source": "env"}
    assert root == tmp_path


def test_falls_back_to_default_filename_in_cwd(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("CONFIG_FILE", raising=False)
    (tmp_path / DEFAULT_CONFIG_FILE).write_text('{"source": "default"}', encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    data, root = load_config_data()

    assert data == {"source": "default"}
    assert root == tmp_path


def test_missing_file_raises_file_not_found(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_config_data(tmp_path / "does_not_exist.json")


def test_malformed_json_raises_value_error(tmp_path: Path):
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(ValueError, match="Failed to parse"):
        load_config_data(bad_file)


def test_expands_user_home_shortcut(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))  # Path.expanduser() on Windows
    (tmp_path / "cfg.json").write_text('{"a": 1}', encoding="utf-8")

    data, root = load_config_data("~/cfg.json")

    assert data == {"a": 1}
    assert root == tmp_path


# --------------------------------------------------------------------------------------
# resolve_environment -- the BC_ENVIRONMENT switch, specific to Business
# Central (which value replaces the `{ENVIRONMENT}` placeholder in each
# tables.yaml URL). Fabric/Factorial/HubSpot uploads don't have a
# per-environment concept and don't read this value.
# --------------------------------------------------------------------------------------


def test_resolve_environment_defaults_to_production():
    assert resolve_environment({}) == "PRODUCTION"


def test_resolve_environment_reads_and_uppercases_env_var():
    assert resolve_environment({"BC_ENVIRONMENT": "sandbox"}) == "SANDBOX"


def test_resolve_environment_blank_value_falls_back_to_default():
    assert resolve_environment({"BC_ENVIRONMENT": "   "}) == "PRODUCTION"


def test_resolve_environment_reads_real_os_environ_by_default(monkeypatch):
    monkeypatch.setenv("BC_ENVIRONMENT", "sandbox")
    assert resolve_environment() == "SANDBOX"
