"""Audit logging for FibAgent agent sessions."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

try:
    from rich.console import Console
    from rich.logging import RichHandler
except ImportError:  # Rich is optional; fall back to standard logging.
    Console = None
    RichHandler = None


CURRENT_DIR = Path(__file__).parent
LOGS_DIR = CURRENT_DIR / "logs"

ACTIVE_LOG_PATH: Path | None = None
TRANSCRIPT_CONSOLE = None
TRANSCRIPT_FILE_HANDLE = None

log = logging.getLogger("agent")


def configure_logging() -> Path:
    """Send logs to both the terminal and a timestamped transcript file."""
    global ACTIVE_LOG_PATH, TRANSCRIPT_CONSOLE, TRANSCRIPT_FILE_HANDLE

    if ACTIVE_LOG_PATH is not None:
        return ACTIVE_LOG_PATH

    LOGS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOGS_DIR / f"agent_log_{timestamp}.log"

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()

    if RichHandler is not None and Console is not None:
        terminal_handler = RichHandler(
            rich_tracebacks=True,
            show_path=False,
            markup=True,
        )
        terminal_handler.setFormatter(logging.Formatter("%(message)s"))

        TRANSCRIPT_FILE_HANDLE = open(log_path, "a", encoding="utf-8")
        TRANSCRIPT_CONSOLE = Console(
            file=TRANSCRIPT_FILE_HANDLE,
            force_terminal=False,
            color_system=None,
        )
        transcript_handler = RichHandler(
            console=TRANSCRIPT_CONSOLE,
            rich_tracebacks=True,
            show_path=False,
            markup=True,
        )
        transcript_handler.setFormatter(logging.Formatter("%(message)s"))
    else:
        terminal_handler = logging.StreamHandler()
        terminal_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))

        TRANSCRIPT_FILE_HANDLE = open(log_path, "a", encoding="utf-8")
        transcript_handler = logging.StreamHandler(TRANSCRIPT_FILE_HANDLE)
        transcript_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))

    root_logger.addHandler(terminal_handler)
    root_logger.addHandler(transcript_handler)

    ACTIVE_LOG_PATH = log_path
    log.info("Audit logging configured: %s", log_path)
    return log_path


def flush_transcript() -> None:
    """Flush the active transcript file, if one is open."""
    if TRANSCRIPT_FILE_HANDLE is not None:
        TRANSCRIPT_FILE_HANDLE.flush()


def active_log_path() -> str | None:
    """Return the active audit log path as a displayable string."""
    return None if ACTIVE_LOG_PATH is None else str(ACTIVE_LOG_PATH)
