"""Acceptance tests - real end-to-end tests with actual network behavior.

These tests use real BC API calls. Requires .env configuration.
Run with: pytest -m acceptance -v

To test retry behavior manually:
1. Run: pytest -m acceptance -v -s
2. During download, disconnect/reconnect internet
3. System should recover automatically
"""

from pathlib import Path

import pytest
from dotenv import load_dotenv

from src.bc_client.config import load_settings
from src.bc_client.auth import OAuthTokenProvider
from src.bc_client.api import BusinessCentralClient
from src.bc_client.exporter import export_table


@pytest.fixture(scope="module", autouse=True)
def load_env():
    """Load .env file before running acceptance tests."""
    load_dotenv()


@pytest.fixture(scope="module")
def settings():
    """Load settings, skip if credentials not configured."""
    try:
        return load_settings()
    except ValueError as e:
        pytest.skip(f"Skipping acceptance tests: {e}")


@pytest.mark.acceptance
def test_full_download_with_real_api(settings, tmp_path: Path) -> None:
    """Test complete download flow with real BC API (bc_job_headers only)."""
    # Keep exports isolated inside the temporary pytest directory.
    settings.output_dir = tmp_path

    # Use only bc_job_headers (smallest table) so downloads stay fast.
    table = next((t for t in settings.tables if t.name == "bc_job_headers"), None)
    if not table:
        pytest.skip("bc_job_headers table not configured")

    token_provider = OAuthTokenProvider(
        token_url=settings.token_url,
        client_id=settings.client_id,
        client_secret=settings.client_secret,
        scope=settings.scope,
    )

    client = BusinessCentralClient(
        settings=settings,
        token_provider=token_provider,
    )

    rows = client.get_table_rows(table.url, label=table.name)

    assert len(rows) > 0, "Should have fetched some rows"

    csv_path = export_table(table.name, rows, tmp_path)
    assert csv_path.exists()
    assert csv_path.stat().st_size > 0

    print(f"\n✓ Downloaded {len(rows)} rows from {table.name}")
    print(f"✓ Exported to {csv_path}")


@pytest.mark.acceptance
def test_retry_behavior_with_real_api(settings, tmp_path: Path) -> None:
    """Test retry mechanism with real BC API (bc_job_headers only).

    Validates retry logic works with real network calls.
    Manually disconnect/reconnect internet during execution to test recovery.
    """
    # Keep exports isolated inside the temporary pytest directory.
    settings.output_dir = tmp_path

    # Use only bc_job_headers (smallest table) so manual retry testing stays quick.
    table = next((t for t in settings.tables if t.name == "bc_job_headers"), None)
    if not table:
        pytest.skip("bc_job_headers table not configured")

    token_provider = OAuthTokenProvider(
        token_url=settings.token_url,
        client_id=settings.client_id,
        client_secret=settings.client_secret,
        scope=settings.scope,
    )

    client = BusinessCentralClient(
        settings=settings,
        token_provider=token_provider,
    )

    print(f"\n>>> Downloading {table.name}... (disconnect internet to test retry) <<<")

    rows = client.get_table_rows(table.url, label=table.name)

    assert len(rows) > 0, "Should have fetched some rows"

    csv_path = export_table(table.name, rows, tmp_path)
    assert csv_path.exists()
    assert csv_path.stat().st_size > 0

    print(f"✓ Successfully downloaded {len(rows)} rows (with retry support)")
    print(f"✓ Exported to {csv_path}")
