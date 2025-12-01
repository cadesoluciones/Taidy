from pathlib import Path

import pytest

from src.bc_client.config import DEFAULT_PAGE_SIZE, Settings, TableConfig, load_settings


def _write_tables_file(
    directory: Path, entries: list[tuple[str, str]] | None = None
) -> Path:
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


def _base_config(tmp_path: Path, *, page_size: int | None = None) -> tuple[dict, Path]:
    tables_file = _write_tables_file(tmp_path)
    config = {
        "business_central": {
            "tenant_id": "tenant",
            "environment": "SANDBOX",
            "client_id": "client",
            "scope": "scope",
            "token_url": "https://example.com/token",
            "company_id": "123",
            "company_name": "Some Company",
            "tables_file": tables_file.name,
            "page_size": 500 if page_size is None else page_size,
            "output_dir": "./out",
        },
        "fabric_upload": {
            "tenant_id": "fabric",
            "client_id": "fabric-client",
            "workspace_name": "Sandbox",
            "lakehouse_name": "Lakehouse",
        },
    }
    return config, tmp_path


def test_load_settings_success(tmp_path: Path) -> None:
    config, config_dir = _base_config(tmp_path)
    settings = load_settings(
        [("BC_CLIENT_SECRET", "secret")],
        config_data=config,
        config_dir=config_dir,
    )

    assert isinstance(settings, Settings)
    assert settings.tenant_id == "tenant"
    assert settings.tables == [
        TableConfig(name="Table A", url="https://example.com/a"),
        TableConfig(name="Table B", url="https://example.com/b"),
    ]
    assert settings.page_size == 500
    expected_output = (config_dir / "out").resolve()
    assert settings.output_dir == expected_output


def test_load_settings_missing_required_secret(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config, config_dir = _base_config(tmp_path)
    monkeypatch.delenv("BC_CLIENT_SECRET", raising=False)

    with pytest.raises(ValueError) as exc:
        load_settings(config_data=config, config_dir=config_dir)

    assert "BC_CLIENT_SECRET" in str(exc.value)


def test_load_settings_invalid_page_size(tmp_path: Path) -> None:
    config, config_dir = _base_config(tmp_path, page_size=0)

    with pytest.raises(ValueError) as exc:
        load_settings(
            [("BC_CLIENT_SECRET", "secret")],
            config_data=config,
            config_dir=config_dir,
        )

    assert "BC_PAGE_SIZE" in str(exc.value)


def test_load_settings_default_config(tmp_path: Path) -> None:
    config, config_dir = _base_config(tmp_path)
    settings = load_settings(
        [("BC_CLIENT_SECRET", "secret")],
        config_data=config,
        config_dir=config_dir,
    )

    assert settings.client_id == config["business_central"]["client_id"]
    assert [table.name for table in settings.tables] == ["Table A", "Table B"]


def test_load_settings_invalid_table_entry(tmp_path: Path) -> None:
    config, config_dir = _base_config(tmp_path)
    tables_path = tmp_path / "tables.yaml"
    tables_path.write_text("tables: invalid", encoding="utf-8")
    config["business_central"]["tables_file"] = tables_path.name

    with pytest.raises(ValueError) as exc:
        load_settings(
            [("BC_CLIENT_SECRET", "secret")],
            config_data=config,
            config_dir=config_dir,
        )

    assert "tables" in str(exc.value)


def test_load_settings_company_id_optional(tmp_path: Path) -> None:
    config, config_dir = _base_config(tmp_path)
    config["business_central"].pop("company_id", None)

    settings = load_settings(
        [("BC_CLIENT_SECRET", "secret")],
        config_data=config,
        config_dir=config_dir,
    )

    assert settings.company_id is None


def test_load_settings_tables_file_missing(tmp_path: Path) -> None:
    config, config_dir = _base_config(tmp_path)
    config["business_central"]["tables_file"] = "missing.yaml"

    with pytest.raises(ValueError) as exc:
        load_settings(
            [("BC_CLIENT_SECRET", "secret")],
            config_data=config,
            config_dir=config_dir,
        )

    assert "missing.yaml" in str(exc.value)


def test_load_settings_tables_file_default(tmp_path: Path) -> None:
    tables_file = _write_tables_file(tmp_path)
    config = {
        "business_central": {
            "tenant_id": "tenant",
            "environment": "SANDBOX",
            "client_id": "client",
            "scope": "scope",
            "token_url": "https://example.com/token",
            "company_id": "123",
            "company_name": "Some Company",
            "tables_file": tables_file.name,
            "output_dir": "./out",
        },
        "fabric_upload": {
            "tenant_id": "fabric",
            "client_id": "fabric-client",
            "workspace_name": "Sandbox",
            "lakehouse_name": "Lakehouse",
        },
    }

    settings = load_settings(
        [("BC_CLIENT_SECRET", "secret")],
        config_data=config,
        config_dir=tmp_path,
    )

    assert [table.name for table in settings.tables] == ["Table A", "Table B"]


def test_load_settings_defaults_page_size_when_missing(tmp_path: Path) -> None:
    config, config_dir = _base_config(tmp_path)
    config["business_central"].pop("page_size", None)

    settings = load_settings(
        [("BC_CLIENT_SECRET", "secret")],
        config_data=config,
        config_dir=config_dir,
    )

    assert settings.page_size == DEFAULT_PAGE_SIZE


def test_load_settings_marks_incremental_tables(tmp_path: Path) -> None:
    config, config_dir = _base_config(tmp_path)
    tables_file = config_dir / config["business_central"]["tables_file"]
    tables_file.write_text(
        "\n".join(
            [
                "tables:",
                "  - name: Incremental",
                "    url: https://example.com/incremental",
                "    incremental: true",
                "  - name: Snapshot",
                "    url: https://example.com/snapshot",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    settings = load_settings(
        [("BC_CLIENT_SECRET", "secret")],
        config_data=config,
        config_dir=config_dir,
    )

    assert settings.tables[0].incremental is True
    assert settings.tables[1].incremental is False
