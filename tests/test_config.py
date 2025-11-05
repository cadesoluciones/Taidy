from __future__ import annotations

import os
from pathlib import Path

import pytest

from bc_client.config import Settings, TableConfig, load_settings


def _write_tables_file(directory: Path, entries: list[tuple[str, str]] | None = None) -> Path:
    entries = entries or [
        ("Table A", "https://example.com/a"),
        ("Table B", "https://example.com/b"),
    ]
    lines = ["tables:"]
    for name, url in entries:
        lines.append(f"  - name: {name}")
        lines.append(f"    url: {url}")
    path = directory / "tables.yaml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _base_env(tmp_path: Path) -> dict[str, str]:
    tables_file = _write_tables_file(tmp_path)
    return {
        "BC_TENANT_ID": "tenant",
        "BC_ENVIRONMENT": "SANDBOX",
        "BC_CLIENT_ID": "client",
        "BC_CLIENT_SECRET": "secret",
        "BC_SCOPE": "scope",
        "BC_TOKEN_URL": "https://example.com/token",
        "BC_COMPANY_ID": "123",
        "BC_COMPANY_NAME": "Some Company",
        "BC_PAGE_SIZE": "500",
        "BC_OUTPUT_DIR": "./out",
        "BC_TABLES_FILE": str(tables_file),
    }


def test_load_settings_success(tmp_path: Path) -> None:
    env = _base_env(tmp_path)
    env["BC_OUTPUT_DIR"] = str(tmp_path / "exports")

    settings = load_settings(env.items())

    assert isinstance(settings, Settings)
    assert settings.tenant_id == "tenant"
    assert settings.tables == [
        TableConfig(name="Table A", url="https://example.com/a"),
        TableConfig(name="Table B", url="https://example.com/b"),
    ]
    assert settings.page_size == 500
    assert settings.output_dir == Path(env["BC_OUTPUT_DIR"]).expanduser()


@pytest.mark.parametrize("missing_key", [
    "BC_TENANT_ID",
    "BC_CLIENT_SECRET",
])
def test_load_settings_missing_required_key(tmp_path: Path, missing_key: str) -> None:
    env = _base_env(tmp_path)
    env.pop(missing_key)

    with pytest.raises(ValueError) as exc:
        load_settings(env.items())

    assert missing_key in str(exc.value)


def test_load_settings_invalid_page_size(tmp_path: Path) -> None:
    env = _base_env(tmp_path)
    env["BC_PAGE_SIZE"] = "0"

    with pytest.raises(ValueError) as exc:
        load_settings(env.items())

    assert "BC_PAGE_SIZE" in str(exc.value)


def test_load_settings_default_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    env = _base_env(tmp_path)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    settings = load_settings()

    assert settings.client_id == env["BC_CLIENT_ID"]
    assert [table.name for table in settings.tables] == ["Table A", "Table B"]


def test_load_settings_invalid_table_entry(tmp_path: Path) -> None:
    env = _base_env(tmp_path)
    tables_file = Path(env["BC_TABLES_FILE"])
    tables_file.write_text("tables: invalid", encoding="utf-8")

    with pytest.raises(ValueError) as exc:
        load_settings(env.items())

    assert "tables" in str(exc.value)


def test_load_settings_company_id_optional(tmp_path: Path) -> None:
    env = _base_env(tmp_path)
    env.pop("BC_COMPANY_ID")

    settings = load_settings(env.items())

    assert settings.company_id is None


def test_load_settings_tables_file_missing(tmp_path: Path) -> None:
    env = _base_env(tmp_path)
    env["BC_TABLES_FILE"] = str(tmp_path / "missing.yaml")

    with pytest.raises(ValueError) as exc:
        load_settings(env.items())

    assert "missing.yaml" in str(exc.value)


def test_load_settings_tables_file_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    default_file = tmp_path / "tables.yaml"
    _write_tables_file(tmp_path)
    monkeypatch.chdir(tmp_path)

    env = _base_env(tmp_path)
    env.pop("BC_TABLES_FILE")
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    settings = load_settings()

    assert [table.name for table in settings.tables] == ["Table A", "Table B"]
