# -*- coding: utf-8 -*-
"""
CLI to trigger a Microsoft Fabric Data Factory pipeline on demand and,
by default, wait for it to finish while logging its status. Designed to be
launched exactly like the other CLIs (`python -m src.fabric_pipelines.cli`),
including from the webapp's subprocess task engine (webapp/tasks.py).
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from typing import Iterable, Optional

from dotenv import load_dotenv

from src.fabric_pipelines.api import TERMINAL_STATUSES, FabricPipelineClient, FabricPipelineError
from src.fabric_pipelines.config import load_settings
from src.utils import configure_logging as configure_rich_logging, get_logger

logger = get_logger(__name__)

DEFAULT_POLL_SECONDS = 15


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Trigger a Fabric Data Factory pipeline on demand")
    parser.add_argument("--pipeline", help="Nombre del pipeline (tal como está en config.json)")
    parser.add_argument(
        "--list",
        action="store_true",
        help="Lista los pipelines (Data Pipeline items) disponibles en el workspace de Fabric y termina",
    )
    parser.add_argument("--no-wait", action="store_true", help="No esperar a que termine, solo lanzarlo")
    parser.add_argument(
        "--poll-seconds", type=int, default=DEFAULT_POLL_SECONDS, help="Cada cuántos segundos consultar el estado"
    )
    parser.add_argument("--verbose", action="store_true", help="Log detallado")
    args = parser.parse_args(list(argv) if argv is not None else None)
    if not args.list and not args.pipeline:
        parser.error("--pipeline es obligatorio (o usa --list para ver los disponibles)")
    return args


def configure_logging(verbose: bool) -> None:
    configure_rich_logging(logging.DEBUG if verbose else logging.INFO)
    if not verbose:
        for name in ("azure.core.pipeline.policies.http_logging_policy", "azure.identity", "urllib3.connectionpool"):
            logging.getLogger(name).setLevel(logging.WARNING)


def run(argv: Optional[Iterable[str]] = None) -> int:
    args = parse_args(argv)
    configure_logging(args.verbose)
    try:
        load_dotenv()
        settings = load_settings()
        client = FabricPipelineClient(settings)

        if args.list:
            discovered = client.list_pipelines()
            if not discovered:
                logger.info("No se encontraron Data Pipeline items en el workspace configurado.")
            for p in discovered:
                logger.info("'%s'  item_id=%s", p["name"], p["item_id"])
            return 0

        pipeline = settings.get_pipeline(args.pipeline)
        logger.info("Lanzando pipeline '%s' (item_id=%s)...", pipeline.name, pipeline.item_id)
        job_instance_id = client.trigger_run(pipeline.item_id)
        logger.info("Pipeline '%s' lanzado. job_instance_id=%s", pipeline.name, job_instance_id)

        if args.no_wait:
            logger.info("No se esperará a que termine (--no-wait). El pipeline sigue corriendo en Fabric.")
            return 0

        while True:
            time.sleep(args.poll_seconds)
            info = client.get_status(pipeline.item_id, job_instance_id)
            status = info.get("status", "Unknown")
            logger.info("Pipeline '%s': estado = %s", pipeline.name, status)
            if status in TERMINAL_STATUSES:
                if status == "Completed":
                    logger.info("Pipeline '%s' completado correctamente.", pipeline.name)
                    return 0
                logger.error(
                    "Pipeline '%s' terminó con estado '%s'. Detalle: %s",
                    pipeline.name,
                    status,
                    info.get("failureReason") or info,
                )
                return 1
    except (FabricPipelineError, ValueError) as exc:
        logger.error("Error al ejecutar el pipeline: %s", exc)
        return 1
    except Exception as exc:  # pragma: no cover
        logger.exception("Fallo inesperado ejecutando el pipeline: %s", exc)
        return 1


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
