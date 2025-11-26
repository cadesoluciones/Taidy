"""Integration tests - test multiple components working together with mocked external APIs."""

from pathlib import Path

import responses

from src.bc_client.api import BusinessCentralClient
from src.bc_client.auth import OAuthTokenProvider
from src.bc_client.config import Settings, TableConfig
from src.bc_client.exporter import export_table


def _settings() -> Settings:
    return Settings(
        tenant_id="tenant",
        environment="Sandbox",
        client_id="client",
        client_secret="secret",
        scope="scope",
        token_url="https://login.microsoftonline.com/tenant/oauth2/v2.0/token",
        company_id="00000000-0000-0000-0000-000000000000",
        company_name="Company",
        tables=[
            TableConfig(
                name="customers",
                url="https://api.businesscentral.dynamics.com/v2.0/tenant/Sandbox/api/data/companies(00000000-0000-0000-0000-000000000000)/customers",
            )
        ],
        page_size=100,
        output_dir=Path("/tmp"),
    )


@responses.activate
def test_auth_and_api_integration(tmp_path: Path) -> None:
    """Test OAuth token provider + API client working together."""
    settings = _settings()
    table = settings.tables[0]

    # Prevent external calls by returning a canned token payload.
    responses.add(
        responses.POST,
        settings.token_url,
        json={"access_token": "real_token_123", "expires_in": 3600},
        status=200,
    )

    # Return a simple table payload so the client can decode rows.
    responses.add(
        responses.GET,
        table.url,
        json={"value": [{"id": 1, "name": "Test"}]},
        status=200,
    )

    # Use the real components to prove the integration surface.
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

    assert len(rows) == 1
    assert rows[0]["name"] == "Test"
    # Confirm the client attached the expected bearer token to the second request.
    assert (
        "Bearer real_token_123" in responses.calls[1].request.headers["Authorization"]
    )


@responses.activate
def test_full_pipeline_integration(tmp_path: Path) -> None:
    """Test complete pipeline: auth -> fetch -> paginate -> export."""
    settings = _settings()
    # Keep exports contained inside pytest's temporary directory.
    settings.output_dir = tmp_path
    table = settings.tables[0]

    # Token endpoint still needs to be stubbed for the OAuth flow.
    responses.add(
        responses.POST,
        settings.token_url,
        json={"access_token": "token", "expires_in": 3600},
        status=200,
    )

    # Respond with nextLink so pagination logic is exercised.
    responses.add(
        responses.GET,
        table.url,
        json={
            "value": [{"id": 1, "name": "Customer 1"}],
            "@odata.nextLink": f"{table.url}?$skiptoken=abc",
        },
        status=200,
    )
    responses.add(
        responses.GET,
        f"{table.url}?$skiptoken=abc",
        json={"value": [{"id": 2, "name": "Customer 2"}]},
        status=200,
    )

    # Use the actual provider + client to wire auth and pagination.
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

    # Fetch data
    rows = client.get_table_rows(table.url, label=table.name)
    assert len(rows) == 2

    # Export to CSV
    csv_path = export_table(table.name, rows, tmp_path)
    assert csv_path.exists()

    # Verify CSV content
    content = csv_path.read_text()
    assert "Customer 1" in content
    assert "Customer 2" in content
