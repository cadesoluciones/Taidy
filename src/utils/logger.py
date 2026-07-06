"""Rich-based logger configuration."""

import logging
from typing import Optional

from rich.console import Console
from rich.logging import RichHandler


_CONSOLE = Console(stderr=True, force_terminal=True)
_DEFAULT_FORMAT = "%(message)s"


def configure_logging(level: Optional[int] = None) -> None:
    """Configure the root logger with Rich output."""
    handler = RichHandler(
        console=_CONSOLE,
        show_time=True,
        show_level=True,
        show_path=False,
        markup=False,
        rich_tracebacks=True,
    )
    handler.setFormatter(logging.Formatter(_DEFAULT_FORMAT))

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(level or logging.INFO)
    root_logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Return a logger that inherits from the configured root handler."""
    return logging.getLogger(name)
