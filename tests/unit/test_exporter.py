import csv
from pathlib import Path

from src.bc_client import exporter


def test_export_table_writes_csv(tmp_path: Path) -> None:
    rows = [
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"},
    ]

    output = exporter.export_table("Customers", rows, tmp_path)

    assert output.exists()
    with output.open(newline="") as fh:
        reader = csv.reader(fh)
        # CSV header should include every field seen across rows.
        assert next(reader) == ["id", "name"]
        assert next(reader) == ["1", "Alice"]
        assert next(reader) == ["2", "Bob"]


def test_export_table_handles_empty_dataset(tmp_path: Path) -> None:
    output = exporter.export_table("Empty Table", [], tmp_path)

    assert output.exists()
    # An empty dataset should produce an empty file (no header written).
    assert output.read_text() == ""


def test_export_table_creates_directory(tmp_path: Path) -> None:
    target_dir = tmp_path / "nested" / "dir"
    rows = [{"id": 1}]

    output = exporter.export_table("General Ledger", rows, target_dir)

    assert output.parent == target_dir
    assert output.name == "general_ledger.csv"
