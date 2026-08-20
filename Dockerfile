# syntax=docker/dockerfile:1

# ---- Stage 1: build the frontend static assets ----
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: backend runtime, serving the built frontend from the same origin ----
FROM python:3.12-slim AS backend

WORKDIR /app

# ODBC Driver 18 for SQL Server -- needed by pyodbc (requirements.txt) to
# query a Fabric Lakehouse's SQL analytics endpoint (bronze./gold. schema
# tables, see src/fabric_pipelines/api.py::list_lakehouse_tables). Microsoft
# only ships this via its own apt repo, not Debian's.
#
# Uses Microsoft's own packages-microsoft-prod.deb helper (registers the
# repo AND its signing key together) rather than hand-adding the repo with
# the generic key from packages.microsoft.com/keys/microsoft.asc --
# confirmed live in a throwaway container: that generic key's fingerprint
# doesn't match the one actually signing the Debian 13 (trixie) repo
# (`apt-get update` fails with "Missing key EE4D7792F748182B"), which is
# the real Debian version python:3.12-slim currently resolves to, not 12
# (bookworm). The .deb helper sidesteps needing to track that manually.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl unixodbc-dev \
    && curl -sSL -o /tmp/packages-microsoft-prod.deb https://packages.microsoft.com/config/debian/13/packages-microsoft-prod.deb \
    && dpkg -i /tmp/packages-microsoft-prod.deb \
    && rm /tmp/packages-microsoft-prod.deb \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
    && apt-get purge -y curl \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY api/ ./api/
COPY webapp/ ./webapp/
COPY src/ ./src/
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Every persisted file (users.db, audit.log, schedules.json, workflows.json,
# run_history.json) moves here instead of next to its owning module -- see
# webapp/state_dir.py. tables.yaml/factorial_tables.yaml/config.json are
# deliberately NOT baked into the image (they're deployment-specific and
# hand-curated) -- mount them at /app/ over this image, see docker-compose.yml.
ENV TAIDY_STATE_DIR=/app/data
RUN mkdir -p /app/data

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
