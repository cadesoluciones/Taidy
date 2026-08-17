# -*- coding: utf-8 -*-
"""
A simple, shared loader for the main JSON configuration file.

This module provides a standardized way to load the `config.json` file, which
contains settings for both Business Central and Fabric uploads. It handles path
resolution, environment variable overrides, and basic error handling for file
access and JSON parsing.
"""

# --------------------------------------------------------------------------------------
# Imports
# --------------------------------------------------------------------------------------

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# --------------------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------------------

# DEFAULT_CONFIG_FILE is the fallback filename if no path is specified via
# argument or environment variable.
DEFAULT_CONFIG_FILE = "config.json"

# DEFAULT_ENVIRONMENT is used when BC_ENVIRONMENT isn't set -- this repo's
# real deployment runs against Production today.
DEFAULT_ENVIRONMENT = "PRODUCTION"


# --------------------------------------------------------------------------------------
# Core Logic
# --------------------------------------------------------------------------------------


def load_config_data(path: str | Path | None = None) -> Tuple[dict[str, Any], Path]:
    """
    Loads the JSON config and returns its content plus the parent directory.

    This function is central to the application's configuration. It resolves the
    path to the config file by checking (in order):
    1. The `path` argument.
    2. The `CONFIG_FILE` environment variable.
    3. The `DEFAULT_CONFIG_FILE` constant.

    It then reads and parses the JSON file, returning the data and the directory
    where the file was found. The parent directory is crucial for resolving
    relative paths defined within the config file (like `tables_file`).

    Args:
        path: An optional direct path to the configuration file.

    Raises:
        FileNotFoundError: If the resolved configuration file path does not exist
                           or is not a file.
        ValueError: If the file cannot be read due to an OS error or if it
                    contains invalid JSON.

    Returns:
        A tuple containing:
        - The parsed JSON data as a dictionary.
        - The absolute `Path` to the parent directory of the config file.
    """
    # Determine the config file path, with robust handling for user shortcuts (~)
    # and ensuring the path is absolute for reliable access.
    config_path = (
        Path(path or os.environ.get("CONFIG_FILE", DEFAULT_CONFIG_FILE))
        .expanduser()
        .resolve()
    )

    # Pre-flight check to ensure the file exists before attempting to read it.
    # This provides a clearer error message than a generic `OSError`.
    if not config_path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    # Read the file with explicit UTF-8 encoding.
    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(
            f"Cannot read configuration file {config_path}: {exc}"
        ) from exc

    # Parse the JSON content, raising a `ValueError` for malformed files.
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Failed to parse configuration file {config_path}: {exc}"
        ) from exc

    # Return the data and the parent directory, which acts as the root for
    # resolving other relative paths in the config.
    return data, config_path.parent


def resolve_environment(env: Optional[Dict[str, str]] = None) -> str:
    """
    Resolves BC_ENVIRONMENT, the Business Central environment switch.

    This is BC-specific: it's the exact environment name Business Central
    itself uses in its OData URLs (e.g. "PRODUCTION", "SANDBOX_CADE"),
    substituted into the `{ENVIRONMENT}` placeholder in each tables.yaml URL
    (see src/bc_client/config.py). Fabric/Factorial/HubSpot uploads don't
    have a per-environment concept and don't read this value.
    """
    raw_env = env if env is not None else os.environ
    value = (raw_env.get("BC_ENVIRONMENT") or DEFAULT_ENVIRONMENT).strip().upper()
    return value or DEFAULT_ENVIRONMENT
