"""Fabric OneLake uploader implementation."""

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
from ..utils import get_logger

logger = get_logger(__name__)


# Note: Using Azure SDK clients directly instead of protocols for simplicity


class FabricUploader:
    """Uploads CSV exports from the local filesystem into Fabric OneLake."""

    def __init__(
        self,
        settings: FabricUploadSettings,
        *,
        file_system_client: Optional[Any] = None,
        now_fn: Optional[Callable[[], datetime]] = None,
        sleep_fn: Optional[Callable[[float], None]] = None,
    ) -> None:
        self._settings = settings
        self._file_system = file_system_client or create_file_system_client(settings)
        self._now = now_fn or (lambda: datetime.now(timezone.utc))
        self._sleep = sleep_fn or time.sleep

    def discover_csv_files(self) -> List[Path]:
        """Return a sorted list of CSV files available under the export root."""
        # Check if export directory exists
        root = self._settings.local_export_root
        if not root.exists():
            logger.debug("Fabric upload root '%s' does not exist", root)
            return []

        # Find all CSV files recursively and sort them
        csv_files = sorted(path for path in root.rglob("*.csv") if path.is_file())
        logger.debug("Discovered %d CSV file(s) under '%s'", len(csv_files), root)
        return csv_files

    def upload_files(self, files: Iterable[Path]) -> tuple[int, int]:
        """Upload the provided CSV files to OneLake."""
        paths = sorted(files)
        if not paths:
            logger.info(
                "No CSV files found for Fabric upload in '%s'",
                self._settings.local_export_root,
            )
            return 0, 0

        uploaded = 0
        skipped = 0
        for local_path in paths:
            remote_path = self._build_remote_path(local_path)
            logger.info("Uploading '%s' to Fabric OneLake", local_path.name)
            logger.debug("Remote path: %s", remote_path)
            if self._upload_with_retry(local_path, remote_path):
                uploaded += 1
            else:
                skipped += 1
        return uploaded, skipped

    def _upload_with_retry(self, local_path: Path, remote_path: str) -> bool:
        attempts = self._settings.max_retries
        for attempt in range(1, attempts + 1):
            try:
                uploaded = self._upload_once(local_path, remote_path)
                if uploaded:
                    logger.info("Successfully uploaded '%s'", local_path.name)
                return uploaded
            except Exception as exc:  # pragma: no cover - exercised in tests via mocks
                if not self._is_retryable(exc) or attempt == attempts:
                    logger.exception(
                        "Upload failed for '%s' after %d attempt(s)",
                        local_path,
                        attempt,
                    )
                    raise
                delay = min(2 ** (attempt - 1), 30)
                logger.warning(
                    "Transient Fabric upload error on attempt %d/%d for '%s': %s",
                    attempt,
                    attempts,
                    local_path,
                    exc,
                )
                self._sleep(float(delay))

    def _upload_once(self, local_path: Path, remote_path: str) -> bool:
        # Get Azure client for the target file
        file_client = self._file_system.get_file_client(remote_path)

        # Check if file already exists in OneLake
        exists = self._file_exists(file_client)
        if not self._settings.overwrite and exists:
            logger.info("Skipping '%s' (already exists)", local_path.name)
            return False

        # Create parent directories if file doesn't exist
        if not exists:
            self._ensure_remote_parent(remote_path)

        # Read local file and upload to OneLake
        data = local_path.read_bytes()
        overwrite_flag = self._settings.overwrite or not exists
        file_client.upload_data(data, overwrite=overwrite_flag)
        return True

    def _file_exists(self, file_client: Any) -> bool:
        try:
            file_client.get_file_properties()
            return True
        except ResourceNotFoundError:
            return False
        except HttpResponseError as exc:
            status = getattr(exc, "status_code", None)
            if status in {400, 404}:
                logger.debug(
                    "Treating HTTP %s during get_file_properties as missing path",
                    status,
                )
                return False
            raise

    def _ensure_remote_parent(self, remote_path: str) -> None:
        parent = PurePosixPath(remote_path).parent
        if str(parent) in {"", "."}:
            return
        try:
            self._file_system.create_directory(parent.as_posix(), exist_ok=True)
        except Exception:  # pragma: no cover - best effort
            logger.debug(
                "Failed to create remote directory '%s'", parent, exc_info=True
            )

    def _build_remote_path(self, local_path: Path) -> str:
        # Validate file is within export root directory
        try:
            _ = local_path.resolve().relative_to(self._settings.local_export_root)
        except ValueError as exc:  # pragma: no cover - defensive
            raise ValueError(
                f"File {local_path} is outside the export root {self._settings.local_export_root}"
            ) from exc

        # Extract table name from filename and sanitize it
        table_segment = self._sanitize_table(local_path.stem)

        run_root = self._settings.local_export_root
        base = PurePosixPath(self._settings.path_prefix)
        base /= self._settings.source_name

        if run_root.name == "full":
            remote_path = base / "full" / f"{table_segment}.csv"
            return remote_path.as_posix()

        if run_root.parent.name == "incremental":
            run_id = run_root.name
            remote_path = base / "incremental" / table_segment / run_id
            remote_path /= local_path.name
            return remote_path.as_posix()

        raise ValueError(f"Unsupported export layout in {run_root}")

    @staticmethod
    def _sanitize_table(raw: str) -> str:
        cleaned = raw.strip().lower().replace(" ", "_")
        cleaned = "".join(ch for ch in cleaned if ch.isalnum() or ch in {"-", "_"})
        cleaned = cleaned.strip("_-")
        if not cleaned:
            raise ValueError("CSV filename must include a valid table name")
        return cleaned

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        if isinstance(exc, ServiceRequestError):
            return True
        if isinstance(exc, HttpResponseError):
            status = getattr(exc, "status_code", None)
            return bool(status and status >= 500)
        return False


def upload_exports_if_enabled(output_dir: Path, *, force: bool = False) -> None:
    """Trigger Fabric uploads when enabled via configuration or CLI."""

    from .config import load_fabric_settings  # Local import to avoid cycles

    settings = load_fabric_settings(output_dir, force_enable=force)
    if settings is None:
        logger.info("Fabric uploads are disabled; skipping OneLake transfer")
        return

    uploader = FabricUploader(settings)
    files = uploader.discover_csv_files()
    uploader.upload_files(files)
