"""Job planning helpers for Business Central ingestions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Mapping, Optional

from src.bc_client.config import TableConfig
from src.fabric_upload.checkpoints import FabricCheckpointStore
from src.utils import get_logger
from src.utils.url import merge_query_params

logger = get_logger(__name__)
WATERMARK_FIELD = "SystemModifiedAt"


@dataclass
class TableExportJob:
    table: TableConfig
    request_url: str
    incremental: bool


@dataclass
class TableExportResult:
    job: TableExportJob
    destination: Path
    new_watermark: Optional[str]
    written: bool


def prepare_export_jobs(
    tables: List[TableConfig],
    checkpoint_store: Optional[FabricCheckpointStore],
    *,
    mode: str = "incremental",
) -> List[TableExportJob]:
    """Plan exports per table, injecting incremental filters when possible."""
    jobs: List[TableExportJob] = []
    for table in tables:
        incremental = supports_incremental(table)
        request_url = table.url

        if incremental:
            if checkpoint_store is None:
                raise RuntimeError(
                    "Incremental tables require Fabric checkpoint configuration"
                )
            checkpoint = checkpoint_store.load(table.name)
            filter_value = checkpoint.watermark_value if checkpoint else None
            params = {}
            params["$orderby"] = f"{WATERMARK_FIELD} asc"

            if mode == "incremental" and filter_value:
                filter_expression = _build_watermark_filter(filter_value)
                params["$filter"] = filter_expression
                logger.info(
                    "Table '%s': applying incremental filter %s",
                    table.name,
                    filter_expression,
                )
            elif mode == "incremental":
                logger.info(
                    "Table '%s': first run without checkpoint; fetching full data but ordering by %s",
                    table.name,
                    WATERMARK_FIELD,
                )
            else:
                logger.info(
                    "Table '%s': running in full snapshot mode (no filters) before updating checkpoint",
                    table.name,
                )

            request_url = merge_query_params(table.url, params)

        jobs.append(
            TableExportJob(
                table=table,
                request_url=request_url,
                incremental=incremental,
            )
        )
    return jobs


def supports_incremental(table: TableConfig) -> bool:
    return bool(table.incremental)


def compute_new_watermark(
    rows: List[Mapping[str, object]],
) -> Optional[str]:
    collected: List[str] = []
    for row in rows:
        raw_value = row.get(WATERMARK_FIELD)
        if raw_value is None:
            continue
        value_str = str(raw_value)
        if not value_str:
            continue
        collected.append(value_str)

    if not collected:
        return None

    return max(collected)


def _build_watermark_filter(watermark_value: str) -> str:
    operator = "gt"
    literal = watermark_value
    return f"{WATERMARK_FIELD} {operator} {literal}"
