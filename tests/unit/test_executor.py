from pathlib import Path

from src.bc_client.config import TableConfig
from src.ingest.executor import _export_single_table
from src.ingest.jobs import TableExportJob


class DummyClient:
    def get_table_rows(self, url: str, *, label: str | None = None):
        return []


def test_export_single_table_skips_empty_incremental(tmp_path: Path) -> None:
    table = TableConfig(
        name="customers",
        url="https://example.com/customers",
        incremental=True,
    )
    job = TableExportJob(
        table=table,
        request_url=table.url,
        incremental=True,
    )
    client = DummyClient()

    result = _export_single_table(job, client, tmp_path)

    assert result.new_watermark is None
    assert not (tmp_path / "customers.csv").exists()
