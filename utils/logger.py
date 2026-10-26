"""
ThinkTank Logging Module

Provides structured logging for all agents and pipeline stages.
"""

import logging
import sys
from pathlib import Path


def get_logger(name: str = "ThinkTank") -> logging.Logger:
    """Create or return a named logger with console and file handlers."""
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger  # Already configured

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s | %(name)-18s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(formatter)
    logger.addHandler(console)

    # File handler (logs to project root)
    log_path = Path(__file__).resolve().parent.parent / "thinktank.log"
    try:
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError:
        logger.warning("Could not create log file at %s", log_path)

    return logger
