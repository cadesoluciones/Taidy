# Business Central Data Extraction PoC

This proof of concept demonstrates how to authenticate against Microsoft Dynamics 365 Business Central, retrieve table data through the OData API, and export the full result set to CSV files. Pagination relies on Business Central’s `@odata.nextLink` along with the `Prefer: odata.maxpagesize=<N>` header so that tables larger than 100 rows are streamed completely. The codebase follows a test-driven approach so that core behaviours (configuration loading, authentication, pagination, exporting, orchestration) remain covered by unit tests.

## Project Layout

- `api_test.py` – CLI entry point that wires configuration, authentication, API client, and CSV exporter.
- `bc_client/` – Supporting modules:
  - `config.py` – environment-driven settings loader
  - `auth.py` – OAuth client credentials flow with token caching
  - `api.py` – Business Central OData wrapper with pagination
  - `exporter.py` – CSV export helpers with safe filenames
- `tests/` – unit tests covering the modules above; hermetic via mocks.

## Prerequisites

- Python 3.12+
- Access to Business Central with an Azure AD application configured for client-credentials.

## Setup Instructions

1. **Create virtual environment and install dependencies (via `uv`)**

   ```bash
   uv venv
   source .venv/bin/activate
   uv pip install -r requirements.txt
   ```

2. **Provide configuration**

   Copy `.env.example` to `.env` for credentials and general settings, then copy `tables.example.yaml` to `tables.yaml` (or another path of your choice) to declare the tables you want to export.

   ```bash
   cp .env.example .env
   cp tables.example.yaml tables.yaml
   $EDITOR .env
   $EDITOR tables.yaml
   ```

   Key variables:

   - `BC_TENANT_ID` – Azure AD tenant ID (GUID).
   - `BC_ENVIRONMENT` – Business Central environment name (e.g., `Sandbox`, `Production`).
   - `BC_CLIENT_ID` / `BC_CLIENT_SECRET` – app registration credentials.
   - `BC_SCOPE` – usually `https://api.businesscentral.dynamics.com/.default`.
   - `BC_COMPANY_ID` – *optional* GUID of the target company (discover via `.../api/data/companies`; leave blank if unknown).
   - `BC_TABLES_FILE` – path to the YAML file describing table names and URLs (defaults to `tables.yaml` if omitted).
   - `BC_PAGE_SIZE` – *optional* pagination chunk size override; defaults to 1000 rows per request and controls the `Prefer: odata.maxpagesize` header.
   - `BC_OUTPUT_DIR` – directory where CSV files will be written.

   The YAML file should look like this:

   ```yaml
   tables:
     - name: Customers
       url: https://api.businesscentral.dynamics.com/v2.0/<TENANT>/<ENV>/api/data/companies(<COMPANY_ID>)/customers
     - name: Vendors
       url: https://api.businesscentral.dynamics.com/v2.0/<TENANT>/<ENV>/api/data/companies(<COMPANY_ID>)/vendors
   ```

   Choose compact `name` values—they will be used for CLI overrides (e.g., `--tables Customers`).

## Running the Automated Tests

Unit tests validate configuration parsing, token lifecycle, pagination logic, CSV exporting, and CLI behaviour. Execute them after each change.

```bash
uv run pytest -q
```

The suite is hermetic and does not require live Business Central access. When you later add integration tests, mark them with `@pytest.mark.integration` so they can be skipped by default.

## Manual Verification Workflow

1. **Dry run** – confirm configuration and table selection without hitting the API:

   ```bash
   uv run python api_test.py --dry-run --verbose

2. **Fetch data** – remove `--dry-run` once credentials are confirmed:

   ```bash
   uv run python api_test.py --verbose

   Optional overrides:

   - `--tables Customers Vendors` – fetch only the listed table names defined in your YAML configuration.
   - `--page-size 1000` – adjust the `Prefer: odata.maxpagesize` hint for large datasets (defaults to 1000 when not set).
   - `--output-dir ./exports_run_$(date +%Y%m%d)` – customize output location.

3. Inspect the generated CSV files under `BC_OUTPUT_DIR`. Files are named after the table (lowercase with underscores) and written atomically to avoid partial results.

## Extending the PoC

- Add integration tests that call the live API using credentials loaded from `.env`, guarded behind an opt-in flag (e.g., `pytest -m integration`).
- Introduce retry/backoff policies (e.g., via `tenacity`) around API calls if rate limiting becomes an issue.
- Stream rows directly to cloud storage (S3, Azure Blob) once CSV export is validated locally.
- Implement incremental sync strategies by tracking last-modified timestamps or using OData filters.

## Troubleshooting

- **Authentication failures** – verify the Azure AD app registration has the `Dynamics 365 Business Central` delegated/ application permissions and that the secret is current.
- **`Missing required configuration` errors** – ensure your `.env` matches `.env.example` and that no keys are blank.
- **Unexpected schema issues** – confirm the table names reference Business Central API entities (see `https://api.businesscentral.dynamics.com/v2.0/<tenant>/<environment>/api/data/$metadata`).

For further debugging, rerun with `--verbose` to emit debug-level logging and inspect HTTP responses.
