# progress.py — Resumability and state tracking for restore
# Author: David Malko

"""ProgressTracker persists restore state across runs.

Manages key_mapping.json (old key -> new key), per-phase completion,
per-item tracking, and user cache for email -> accountId resolution.
"""

import logging
import os
from typing import Any

from jira_tool.utils import load_json, save_json

logger = logging.getLogger("jira_tool")


class ProgressTracker:
    """Tracks restore progress for resumability."""

    def __init__(
        self, backup_dir: str, *, dry_run: bool = False,
    ) -> None:
        self.backup_dir = backup_dir
        self._dry_run = dry_run
        self._mapping_path = os.path.join(backup_dir, "key_mapping.json")
        self._progress_path = os.path.join(
            backup_dir, "restore_progress.json",
        )
        self._user_cache_path = os.path.join(
            backup_dir, "user_cache.json",
        )

        if dry_run:
            # Dry run: start with empty state, never write to disk
            self._key_mapping: dict[str, str] = {}
            self._progress: dict[str, Any] = {}
            self._user_cache: dict[str, str | None] = {}
        else:
            self._key_mapping = self._load_or_empty(
                self._mapping_path,
            )
            self._progress = self._load_or_empty(
                self._progress_path,
            )
            self._user_cache = self._load_or_empty(
                self._user_cache_path,
            )

    # ------------------------------------------------------------------
    # Key mapping (original issue key -> cloud issue key)
    # ------------------------------------------------------------------

    @property
    def key_mapping(self) -> dict[str, str]:
        """Current original -> cloud key mapping."""
        return self._key_mapping

    def map_key(self, orig_key: str, cloud_key: str) -> None:
        """Record a key mapping and persist immediately."""
        self._key_mapping[orig_key] = cloud_key
        if not self._dry_run:
            save_json(self._key_mapping, self._mapping_path)

    def get_cloud_key(self, orig_key: str) -> str | None:
        """Look up cloud key for an original key."""
        return self._key_mapping.get(orig_key)

    def is_issue_created(self, orig_key: str) -> bool:
        """Check if an issue was already created in Cloud."""
        return orig_key in self._key_mapping

    # ------------------------------------------------------------------
    # Phase tracking
    # ------------------------------------------------------------------

    def mark_phase_complete(self, phase: str) -> None:
        """Mark a restore phase as fully complete."""
        phases = self._progress.setdefault("completed_phases", [])
        if phase not in phases:
            phases.append(phase)
            self._save_progress()
        logger.info("Phase '%s' marked complete", phase)

    def is_phase_complete(self, phase: str) -> bool:
        """Check if a phase was already completed."""
        return phase in self._progress.get("completed_phases", [])

    # ------------------------------------------------------------------
    # Per-item tracking within a phase
    # ------------------------------------------------------------------

    def mark_item_done(self, phase: str, item_id: str) -> None:
        """Mark a specific item within a phase as done."""
        items = self._progress.setdefault("items", {})
        phase_items = items.setdefault(phase, [])
        if item_id not in phase_items:
            phase_items.append(item_id)
            self._save_progress()

    def is_item_done(self, phase: str, item_id: str) -> bool:
        """Check if a specific item was already processed."""
        items = self._progress.get("items", {})
        return item_id in items.get(phase, [])

    # ------------------------------------------------------------------
    # User cache (email -> accountId)
    # ------------------------------------------------------------------

    @property
    def user_cache(self) -> dict[str, str | None]:
        """Cached email -> accountId mappings."""
        return self._user_cache

    def cache_user(self, email: str, account_id: str | None) -> None:
        """Cache a user lookup result and persist."""
        self._user_cache[email] = account_id
        if not self._dry_run:
            save_json(self._user_cache, self._user_cache_path)

    def get_cached_user(self, email: str) -> tuple[bool, str | None]:
        """Check user cache.

        Returns:
            (found, account_id) — found is True if email is in cache
            (even if account_id is None, meaning user doesn't exist).
        """
        if email in self._user_cache:
            return True, self._user_cache[email]
        return False, None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _save_progress(self) -> None:
        """Persist progress state to disk."""
        if not self._dry_run:
            save_json(self._progress, self._progress_path)

    @staticmethod
    def _load_or_empty(path: str) -> dict:
        """Load JSON file or return empty dict if not found."""
        if os.path.exists(path):
            try:
                return load_json(path)
            except Exception as exc:
                logger.warning(
                    "Could not load %s: %s — starting fresh",
                    path, exc,
                )
        return {}
