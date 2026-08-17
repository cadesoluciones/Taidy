#!/usr/bin/env bash
# Makes sure everything docker-compose.yml expects to bind-mount from the
# project root actually exists *as the right kind of thing* before `docker
# compose up` ever runs.
#
# Why this exists: config.json/tables.yaml/factorial_tables.yaml
# are deliberately excluded from the image (.dockerignore) and bind-mounted from
# the host instead, so they can be hand-edited without rebuilding. But if the
# host path is missing when Compose tries to bind-mount it, Docker silently
# creates an EMPTY DIRECTORY at that path (both on the host and in the
# container) instead of failing — the app then crashes trying to parse a
# directory as JSON/YAML, and you're left with a stray directory that has to
# be deleted by hand before a real file can go there. This script runs first
# so that never happens.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

# git-tracked config: config.json/tables.yaml/factorial_tables.yaml
# are committed with this deployment's real (non-secret) settings -- if one is
# missing, or is a directory (the Docker footgun above from a previous
# attempt), restore the tracked version instead of inventing placeholder
# content that could silently diverge from what's actually configured.
restore_tracked_file() {
  local path="$1"
  if [ -d "$path" ]; then
    if [ -z "$(ls -A "$path" 2>/dev/null)" ]; then
      echo "docker-bootstrap: '$path' is an empty directory (Docker's missing-bind-mount artifact) -- removing it."
      rmdir "$path"
    else
      echo "docker-bootstrap: ERROR -- '$path' exists but is a non-empty directory, expected a file. Not touching it; resolve by hand." >&2
      return 1
    fi
  fi
  if [ ! -f "$path" ]; then
    echo "docker-bootstrap: '$path' is missing -- restoring the version tracked in git."
    git show "HEAD:$path" > "$path"
  fi
}

restore_tracked_file config.json
restore_tracked_file tables.yaml
restore_tracked_file factorial_tables.yaml
restore_tracked_file hubspot_tables.yaml

# Plain directories -- Docker already auto-creates a missing bind-mount
# directory correctly (no footgun here), this is just belt-and-suspenders so
# they exist with the right permissions before the first run either way.
mkdir -p exports exports_factorial exports_hubspot

# .env holds real secrets (BC/Factorial/Fabric credentials) that can't be
# auto-filled -- but an entirely missing .env hits the same "Docker invents
# something weird" risk via env_file, so seed it from the template and make
# it impossible to miss that it still needs real values.
if [ ! -f .env ]; then
  cp .env.example .env
  echo
  echo "docker-bootstrap: created .env from .env.example -- edit it with real secrets"
  echo "docker-bootstrap: (BC_CLIENT_SECRET, FACTORIAL_API_KEY, HUBSPOT_API_KEY, FABRIC_CLIENT_SECRET, ...) before continuing."
  echo
fi

echo "docker-bootstrap: done."
