# Use an official Python 3.12 slim image.
FROM python:3.12-slim

# ----------------------------
# Runtime / Python defaults
# ----------------------------
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# ----------------------------
# System deps
# - curl + ca-certificates needed to download Task installer
# - build-essential helps when wheels need compiling
# ----------------------------
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      curl \
      ca-certificates \
      build-essential \
 && rm -rf /var/lib/apt/lists/*

# ----------------------------
# Install uv (fast pip replacement)
# ----------------------------
RUN pip install --no-cache-dir uv

# ----------------------------
# Install Taskfile (task)
# Using the official install script and pinning a version.
# ----------------------------
ARG TASK_VERSION=v3.43.3
RUN sh -c "$(curl --location https://taskfile.dev/install.sh)" -- \
      -d -b /usr/local/bin ${TASK_VERSION} \
 && task --version
# Official script + version pin supported by Task docs. :contentReference[oaicite:0]{index=0}

# ----------------------------
# Dependency layer
# Copy only dependency metadata first for better caching.
# ----------------------------
COPY pyproject.toml uv.lock .python-version .

# Project sources are required for editable install (-e).
COPY src/ ./src/

# Install dependencies + project using uv.
# --system installs into the container's global site-packages (normal for Docker).
RUN uv sync
# uv Docker integration guidance recommends separating dependency metadata. :contentReference[oaicite:1]{index=1}

# ----------------------------
# App/runtime files
# ----------------------------
COPY config.json .
COPY tables.yaml .
COPY Taskfile.yml .

# Default to running Taskfile tasks.
ENTRYPOINT ["task"]
CMD ["--", "--help"]
