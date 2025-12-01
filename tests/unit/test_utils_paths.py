from pathlib import Path

import pytest

from src.utils.paths import coerce_dir, sanitize_segment, table_filename


def test_coerce_dir_resolves_and_expands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home_dir = tmp_path / "home"
    target = home_dir / "exports"
    target.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home_dir))

    result = coerce_dir("~/exports")

    assert result == target.resolve()


def test_coerce_dir_requires_existing_when_flag_enabled(tmp_path: Path) -> None:
    missing = tmp_path / "missing"

    with pytest.raises(FileNotFoundError):
        coerce_dir(missing, must_exist=True)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Customers", "customers"),
        (" sales orders ", "sales_orders"),
        ("Invoices-2024!", "invoices-2024"),
    ],
)
def test_sanitize_segment_normalizes_names(raw: str, expected: str) -> None:
    assert sanitize_segment(raw) == expected


def test_table_filename_appends_suffix() -> None:
    assert table_filename("Customers") == "customers.csv"
    assert table_filename("Data", suffix=".json") == "data.json"
