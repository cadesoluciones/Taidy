# -*- coding: utf-8 -*-
"""
Uploads locally exported CSV files to Microsoft Fabric OneLake.

This module contains the `FabricUploader` class, which handles discovering
local CSV files, constructing their corresponding destination paths in OneLake,
and performing the upload with retries for network resilience.
"""

# --------------------------------------------------------------------------------------
# Imports
# --------------------------------------------------------------------------------------

import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable, List, Optional

from azure.core.exceptions import (
    HttpResponseError,
    ResourceNotFoundError,
    ServiceRequestError,
)

from .client_factory import create_file_system_client
from .config import FabricUploadSettings
from ..utils import get_logger, sanitize_segment, table_filename

# --------------------------------------------------------------------------------------
# Constants and Global Variables
# --------------------------------------------------------------------------------------

logger = get_logger(__name__)


# --------------------------------------------------------------------------------------
# Core Uploader Class
# --------------------------------------------------------------------------------------


class FabricUploader:
    """
    Handles the discovery and upload of local CSV export files to Fabric OneLake.
    """

    def __init__(
        self,
        settings: FabricUploadSettings,
        *,
        file_system_client: Optional[Any] = None,
        now_fn: Optional[Callable[[], datetime]] = None,
        sleep_fn: Optional[Callable[[float], None]] = None,
    ) -> None:
        """
        Initializes the FabricUploader.

        Args:
            settings: The Fabric upload settings.
            file_system_client: An optional pre-configured Azure file system client
                                for testing.
            now_fn: An optional function for getting the current time, for testing.
            sleep_fn: An optional function for sleeping, for testing retries.
        """
        self._settings = settings
        self._file_system = file_system_client or create_file_system_client(settings)
        self._now = now_fn or (lambda: datetime.now(timezone.utc))
        self._sleep = sleep_fn or time.sleep
        self._remote_base = settings.remote_base

    def discover_csv_files(self) -> List[Path]:
        """
        Finds all `.csv` files within the configured local export root directory.

        Returns:
            A sorted list of `Path` objects for the discovered CSV files.
        """
        root = self._settings.local_export_root
        if not root.exists():
            logger.debug(
                "Fabric upload root '%s' does not exist, no files to upload.", root
            )
            return []

        # `rglob` recursively finds all matching files.
        csv_files = sorted(path for path in root.rglob("*.csv") if path.is_file())
        logger.debug("Discovered %d CSV file(s) under '%s'", len(csv_files), root)
        return csv_files

    def upload_files(self, files: Iterable[Path]) -> tuple[int, int, int]:
        """
        Uploads a given list of local files to Fabric OneLake.

        A single file exhausting its retries (or hitting a non-retryable
        error) is recorded as failed and does NOT abort the remaining
        files -- previously an uncaught exception from one file propagated
        out of this whole method, silently turning a partially-successful
        batch into a total reported failure and skipping every file after
        the one that failed.

        Args:
            files: An iterable of `Path` objects for the local files to upload.

        Returns:
            A tuple of (uploaded, skipped, failed) counts.
        """
        paths = sorted(files)
        if not paths:
            logger.info(
                "No CSV files found for Fabric upload in '%s'",
                self._settings.local_export_root,
            )
            return 0, 0, 0

        uploaded = 0
        skipped = 0
        failed = 0
        for local_path in paths:
            # Each local file path is mapped to a structured remote path.
            remote_path = self._build_remote_path(local_path)
            logger.info("Uploading '%s' to Fabric OneLake...", local_path.name)
            logger.debug("Remote path will be: %s", remote_path.as_posix())

            try:
                if self._upload_with_retry(local_path, remote_path):
                    uploaded += 1
                else:
                    skipped += 1
            except Exception:
                # _upload_with_retry already logged the exception (including
                # the "Upload failed for '<name>'" line adapter.py's log
                # parser matches); here we only need to keep going.
                failed += 1

        return uploaded, skipped, failed

    def _upload_with_retry(self, local_path: Path, remote_path: PurePosixPath) -> bool:
        """
        Manages the upload process for a single file with an exponential backoff retry
        mechanism for transient network errors.

        Returns:
            `True` if the file was uploaded, `False` if it was skipped.
        """
        attempts = self._settings.max_retries
        for attempt in range(1, attempts + 1):
            try:
                # `_upload_once` returns False if the file is skipped, not on error.
                uploaded = self._upload_once(local_path, remote_path)
                if uploaded:
                    logger.info("Successfully uploaded '%s'", local_path.name)
                return uploaded
            except Exception as exc:
                # If the error is not retryable or we've run out of attempts, re-raise.
                if not self._is_retryable(exc) or attempt == attempts:
                    logger.exception(
                        "Upload failed for '%s' after %d attempt(s).",
                        local_path,
                        attempt,
                    )
                    raise
                # Calculate exponential backoff delay.
                delay = min(2 ** (attempt - 1), 30)  # Cap delay at 30s.
                logger.warning(
                    "Transient Fabric upload error on attempt %d/%d for '%s': %s. "
                    "Retrying in %d seconds...",
                    attempt,
                    attempts,
                    local_path,
                    exc,
                    delay,
                )
                self._sleep(float(delay))
        return False  # Should be unreachable

    def _upload_once(self, local_path: Path, remote_path: PurePosixPath) -> bool:
        """
        Performs a single attempt to upload a file.

        Returns:
            `True` if uploaded, `False` if skipped because it already exists.
        """
        file_client = self._file_system.get_file_client(remote_path.as_posix())

        # First, check if the file already exists in OneLake.
        exists = self._file_exists(file_client)
        if not self._settings.overwrite and exists:
            logger.info(
                "Skipping '%s' because it already exists in OneLake.", local_path.name
            )
            return False

        # Ensure the destination directory exists.
        if not exists:
            self._ensure_remote_parent(remote_path)

        # Read the local file content and upload it.
        data = local_path.read_bytes()
        # The overwrite flag must be explicitly managed.
        overwrite_flag = self._settings.overwrite or not exists
        file_client.upload_data(data, overwrite=overwrite_flag)
        return True

    def _file_exists(self, file_client: Any) -> bool:
        """
        Checks if a file exists in OneLake using its properties.
        Robustly handles different kinds of "not found" errors.
        """
        try:
            file_client.get_file_properties()
            return True
        except ResourceNotFoundError:
            # This is the standard "not found" exception.
            return False
        except HttpResponseError as exc:
            # Some Fabric behaviors might return a 400 or 404 status code
            # in an HttpResponseError instead of a ResourceNotFoundError.
            # We treat these as "not found" to be safe.
            status = getattr(exc, "status_code", None)
            if status in {400, 404}:
                logger.debug(
                    "Treating HTTP %s during get_file_properties as a missing path.",
                    status,
                )
                return False
            # Any other HTTP error is unexpected and should be raised.
            raise

    def _ensure_remote_parent(self, remote_path: PurePosixPath) -> None:
        """
        Creates the parent directory for a remote path if it doesn't exist.
        This is a "best-effort" operation.
        """
        parent = remote_path.parent
        if str(parent) in {"", "."}:
            return
        try:
            self._file_system.create_directory(str(parent))
        except Exception:  # pragma: no cover
            logger.debug(
                "Failed to create remote directory '%s', assuming it exists.",
                parent,
                exc_info=True,
            )

    def _build_remote_path(self, local_path: Path) -> PurePosixPath:
        """
        Constructs the structured remote path in OneLake based on the local file's
        location (e.g., 'full' vs. 'incremental').

        - Full: `raw/business_central/full/<table_name>.csv`
        - Incremental: `raw/business_central/incremental/<table_name>/<run_id>/<filename>.csv`
        """
        # Security check: ensure we are only uploading files from the expected dir.
        try:
            _ = local_path.resolve().relative_to(self._settings.local_export_root)
        except ValueError as exc:  # pragma: no cover
            raise ValueError(
                f"File {local_path} is outside the configured export root "
                f"{self._settings.local_export_root}"
            ) from exc

        table_segment = sanitize_segment(local_path.stem)
        run_root = self._settings.local_export_root

        # Logic for full exports.
        if run_root.name == "full":
            return self._remote_base / "full" / table_filename(local_path.stem)

        # Logic for incremental exports.
        if run_root.parent.name == "incremental":
            run_id = run_root.name
            return (
                self._remote_base
                / "incremental"
                / table_segment
                / run_id
                / local_path.name
            )

        raise ValueError(f"Unsupported export layout in path: {run_root}")

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        """
        Determines if an exception indicates a transient error that can be retried.
        Retryable errors include connection errors and server-side (5xx) HTTP errors.
        """
        if isinstance(exc, ServiceRequestError):
            return True
        if isinstance(exc, HttpResponseError):
            status = getattr(exc, "status_code", None)
            return bool(status and status >= 500)
        return False


# --------------------------------------------------------------------------------------
# Public Functions
# --------------------------------------------------------------------------------------


def upload_exports_if_enabled(output_dir: Path, *, force: bool = False) -> None:
    """
    A convenience wrapper that triggers Fabric uploads only if they are enabled
    in the configuration.

    Args:
        output_dir: The local directory containing the exported files to upload.
        force: If True, forces the upload even if `enabled` is false in config.
    """
    # Use a local import to avoid circular dependency issues between
    # the uploader and config modules.
    from .config import load_fabric_settings

    settings = load_fabric_settings(output_dir, force_enable=force)
    if settings is None:
        logger.info("Fabric uploads are disabled; skipping OneLake transfer.")
        return

    uploader = FabricUploader(settings)
    files = uploader.discover_csv_files()
    if files:
        uploader.upload_files(files)
    else:
        logger.info("No new files found in '%s' to upload.", output_dir)
