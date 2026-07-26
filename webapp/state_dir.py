# -*- coding: utf-8 -*-
"""
Shared helper for where Taidy's persisted JSON/SQLite/YAML state files live.

Every one of these files defaults to living next to the module that owns it
(unchanged local-dev behavior) -- but a container's own filesystem is
ephemeral, so Docker deployments set TAIDY_STATE_DIR to a mounted volume and
every persisted file moves there instead, with no other code change needed.
"""

from __future__ import annotations

import os
from pathlib import Path


def state_path(filename: str, default_dir: Path) -> Path:
    override = os.environ.get("TAIDY_STATE_DIR")
    return (Path(override) if override else default_dir) / filename
