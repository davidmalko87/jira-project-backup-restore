# config.py — Load and validate configuration from .env
# Author: David Malko

"""Configuration loader for Jira Backup & Restore Tool.

Reads settings from .env file using python-dotenv.
All credentials and tunables are centralized here.
"""

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class JiraConfig:
    """All configuration for the Jira Backup & Restore tool."""

    # Jira instance
    jira_url: str = ""
    email: str = ""
    api_token: str = ""
    cookie_header: str = ""
    verify_ssl: bool = True

    # Backup settings
    backup_root: str = "./backups"
    page_size: int = 100
    max_retries: int = 3
    read_timeout: int = 30  # seconds per request; 0 = no timeout
    api_delay: float = 0.2
    chunk_size: int = 8192

    # Backup toggles
    include_attachments: bool = True
    include_changelog: bool = True
    include_worklogs: bool = True

    # Standalone attachment uploader
    legacy_key_jql_template: str = ""

    def validate(self) -> list[str]:
        """Return list of validation errors, empty if config is valid."""
        errors: list[str] = []

        if not self.jira_url:
            errors.append("JIRA_URL is required")
        elif self.jira_url.endswith("/"):
            self.jira_url = self.jira_url.rstrip("/")

        if not self.api_token and not self.cookie_header:
            errors.append(
                "Either JIRA_API_TOKEN or JIRA_COOKIE_HEADER must be set"
            )

        if self.api_token and not self.email:
            errors.append(
                "JIRA_EMAIL is required when using API token auth"
            )

        if self.page_size < 1 or self.page_size > 100:
            errors.append("PAGE_SIZE must be between 1 and 100")

        return errors


def load_config(env_path: str | None = None) -> JiraConfig:
    """Load configuration from .env file.

    Args:
        env_path: Path to .env file. If None, searches current dir.

    Returns:
        Populated JiraConfig instance.

    Raises:
        SystemExit: If .env not found or validation fails.
    """
    if env_path:
        dotenv_path = Path(env_path)
    else:
        dotenv_path = Path(".env")

    if not dotenv_path.exists():
        print(f"[!] Config file not found: {dotenv_path.resolve()}")
        print("    Copy .env.example to .env and fill in your values.")
        sys.exit(1)

    load_dotenv(dotenv_path)

    def _bool(key: str, default: bool = True) -> bool:
        val = os.getenv(key, str(default)).lower()
        return val in ("true", "1", "yes")

    def _int(key: str, default: int) -> int:
        try:
            return int(os.getenv(key, str(default)))
        except ValueError:
            return default

    def _float(key: str, default: float) -> float:
        try:
            return float(os.getenv(key, str(default)))
        except ValueError:
            return default

    config = JiraConfig(
        jira_url=os.getenv("JIRA_URL", ""),
        email=os.getenv("JIRA_EMAIL", ""),
        api_token=os.getenv("JIRA_API_TOKEN", ""),
        cookie_header=os.getenv("JIRA_COOKIE_HEADER", ""),
        verify_ssl=_bool("JIRA_VERIFY_SSL", True),
        backup_root=os.getenv("BACKUP_ROOT", "./backups"),
        page_size=_int("PAGE_SIZE", 100),
        max_retries=_int("MAX_RETRIES", 3),
        read_timeout=_int("READ_TIMEOUT", 30),
        api_delay=_float("API_DELAY", 0.2),
        chunk_size=_int("CHUNK_SIZE", 8192),
        include_attachments=_bool("INCLUDE_ATTACHMENTS", True),
        include_changelog=_bool("INCLUDE_CHANGELOG", True),
        include_worklogs=_bool("INCLUDE_WORKLOGS", True),
        legacy_key_jql_template=os.getenv("LEGACY_KEY_JQL_TEMPLATE", ""),
    )

    errors = config.validate()
    if errors:
        print("[!] Configuration errors:")
        for err in errors:
            print(f"    - {err}")
        sys.exit(1)

    return config
