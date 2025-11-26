"""Simple loader for the shared JSON configuration file."""

import json
import os
from pathlib import Path
from typing import Any, Tuple

DEFAULT_CONFIG_FILE = "config.json"


def load_config_data(path: str | Path | None = None) -> Tuple[dict[str, Any], Path]:
    """Load the JSON config and return its content plus the parent directory."""

    config_path = (
        Path(path or os.environ.get("CONFIG_FILE", DEFAULT_CONFIG_FILE))
        .expanduser()
        .resolve()
    )
    if not config_path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(
            f"Cannot read configuration file {config_path}: {exc}"
        ) from exc

    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ValueError(
            f"Failed to parse configuration file {config_path}: {exc}"
        ) from exc

    return data, config_path.parent
