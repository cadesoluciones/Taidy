"""Execution helpers for Business Central export jobs."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional

from src.bc_client.api import BusinessCentralClient
from src.bc_client.auth import OAuthTokenProvider
from src.bc_client.config import Settings
from src.bc_client.exporter import export_table
from src.fabric_upload.checkpoints import FabricCheckpointStore
from src.ingest.jobs import TableExportJob, TableExportResult, compute_new_watermark
from src.utils import get_logger

logger = get_logger(__name__)


def run_exports(
    jobs: List[TableExportJob],
    settings: Settings,
    checkpoint_store: Optional[FabricCheckpointStore],
    parallel_workers: int,
) -> tuple[int, int]:
    token_provider = _create_token_provider(settings)

    if parallel_workers <= 1:
        client = _create_client(settings, token_provider)
        written = 0
        for job in jobs:
            result = _export_single_table(job, client, settings.output_dir)
            _persist_checkpoint(result, checkpoint_store)
            written += int(result.written)
        return len(jobs), written

    logger.info("Running exports with up to %d parallel workers", parallel_workers)

    def worker(job: TableExportJob) -> TableExportResult:
        client = _create_client(settings, token_provider)
        return _export_single_table(job, client, settings.output_dir)

    errors: List[Exception] = []
    with ThreadPoolExecutor(max_workers=parallel_workers) as executor:
        results = list(executor.map(worker, jobs))

    written = 0
    for job, result in zip(jobs, results):
        try:
            _persist_checkpoint(result, checkpoint_store)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Export failed for table '%s'", job.table.name)
            errors.append(exc)
        written += int(result.written)

    if errors:
        raise RuntimeError("One or more table exports failed") from errors[0]
    return len(jobs), written


def log_dry_run(jobs: List[TableExportJob], output_dir: Path) -> None:
    for job in jobs:
        logger.info(
            "[dry-run] would export table '%s' from %s to %s",
            job.table.name,
            job.request_url,
            output_dir,
        )


def _export_single_table(
    job: TableExportJob,
    client: BusinessCentralClient,
    output_dir: Path,
) -> TableExportResult:
    table = job.table
    logger.info("Exporting table '%s'", table.name)

    rows = client.get_table_rows(job.request_url, label=table.name)
    if job.incremental and not rows:
        logger.info(
            "Table '%s': no new rows; skipping CSV creation",
            table.name,
        )
        destination = output_dir / f"{table.name}.csv"
        return TableExportResult(
            job=job, destination=destination, new_watermark=None, written=False
        )
    destination = export_table(table.name, rows, output_dir)
    new_watermark = compute_new_watermark(rows)

    logger.info("Saved %s", destination)
    return TableExportResult(
        job=job, destination=destination, new_watermark=new_watermark, written=True
    )


def _persist_checkpoint(
    result: TableExportResult,
    checkpoint_store: Optional[FabricCheckpointStore],
) -> None:
    job = result.job
    if not job.incremental:
        return
    if checkpoint_store is None:
        raise RuntimeError("Checkpoint store not initialized for incremental table")
    if result.new_watermark is None:
        logger.info(
            "Table '%s': no rows changed since last watermark; checkpoint unchanged",
            job.table.name,
        )
        return
    checkpoint_store.save(
        job.table.name,
        result.new_watermark,
        watermark_column="SystemModifiedAt",
    )


def _create_token_provider(settings: Settings) -> OAuthTokenProvider:
    return OAuthTokenProvider(
        token_url=settings.token_url,
        client_id=settings.client_id,
        client_secret=settings.client_secret,
        scope=settings.scope,
        session=None,
        timeout=30,
    )


def _create_client(
    settings: Settings,
    token_provider: OAuthTokenProvider,
) -> BusinessCentralClient:
    return BusinessCentralClient(
        settings=settings,
        token_provider=token_provider,
        session=None,
        timeout=30,
    )
