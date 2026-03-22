# utils.py — Shared utilities for Jira Backup & Restore Tool
# Author: David Malko

"""Shared helpers: logging setup, JSON I/O, filename sanitization."""

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any


def setup_logging(log_dir: str = ".", name: str = "jira_tool") -> logging.Logger:
    """Configure dual logging: file (DEBUG) + console (INFO).

    Args:
        log_dir: Directory for log file.
        name: Logger name.

    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"{name}_{timestamp}.log")

    # File handler — DEBUG level, captures everything
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    # Console handler — INFO level, user-facing
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(message)s"))

    logger.addHandler(fh)
    logger.addHandler(ch)

    logger.info(f"Log file: {log_file}")
    return logger


def sanitize_filename(name: str) -> str:
    """Strip characters illegal in Windows/Linux filenames."""
    return re.sub(r'[\\/:*?"<>|]', '_', name)


def load_json(path: str) -> Any:
    """Read and parse a JSON file.

    Args:
        path: Path to JSON file.

    Returns:
        Parsed JSON data.

    Raises:
        FileNotFoundError: If file does not exist.
        json.JSONDecodeError: If file is not valid JSON.
    """
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: Any, path: str) -> None:
    """Write data to a JSON file with pretty formatting.

    Args:
        data: Data to serialize.
        path: Output file path (directories created automatically).
    """
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def utc_now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()
