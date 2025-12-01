"""Minimal path helpers shared across the CLI and core modules."""

from pathlib import Path


def coerce_dir(raw: str | Path, *, must_exist: bool = False) -> Path:
    """
    Normalize a directory provided by the user.

    Expands ``~`` shortcuts, resolves the absolute path, and optionally checks
    that the directory already exists.
    """
    candidate = Path(raw).expanduser().resolve(strict=False)
    if must_exist and not candidate.exists():
        raise FileNotFoundError(f"Directory not found: {candidate}")
    return candidate


def sanitize_segment(value: str) -> str:
    """
    Return a lowercase, underscore-separated version of ``value`` that is safe to embed in a path.
    """
    cleaned = value.strip().lower().replace(" ", "_")
    cleaned = "".join(ch for ch in cleaned if ch.isalnum() or ch in {"-", "_"})
    cleaned = cleaned.strip("_-")
    if not cleaned:
        raise ValueError("Value must contain alphanumeric characters")
    return cleaned


def table_filename(name: str, *, suffix: str = ".csv") -> str:
    """Produce a sanitized filename for a table export."""
    return f"{sanitize_segment(name)}{suffix}"
