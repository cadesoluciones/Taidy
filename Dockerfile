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
