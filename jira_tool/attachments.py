# attachments.py — Standalone attachment uploader
# Author: David Malko

"""Standalone attachment uploader for cases where issues were restored
by another tool (CSV import, manual creation, etc.) and only
attachments need to be uploaded separately.

Supports two issue resolution strategies:
  1. key_mapping.json — if available from a prior restore run
  2. JQL query — search by original key stored in a custom field
"""

import logging
import os

from jira_tool.api_client import JiraApiError, JiraClient
from jira_tool.config import JiraConfig
from jira_tool.progress import ProgressTracker

logger = logging.getLogger("jira_tool")


class AttachmentUploader:
    """Upload attachments to Jira Cloud issues."""

    def __init__(
        self,
        client: JiraClient,
        config: JiraConfig,
    ) -> None:
        self.client = client
        self.config = config

    def upload_from_backup(
        self,
        backup_dir: str,
        project_key: str,
        dry_run: bool = False,
        skip_existing: bool = True,
    ) -> None:
        """Upload attachments from a backup directory.

        Tries key_mapping.json first. Falls back to JQL lookup
        if configured via LEGACY_KEY_JQL_TEMPLATE in .env.

        Args:
            backup_dir: Path to backup directory.
            project_key: Target Jira Cloud project key.
            dry_run: If True, log actions without uploading.
            skip_existing: If True, skip files already attached.
        """
        att_dir = os.path.join(backup_dir, "attachments")
        if not os.path.isdir(att_dir):
            logger.error(
                "Attachments directory not found: %s", att_dir,
            )
            return

        # Try to load key mapping from prior restore
        progress = ProgressTracker(backup_dir)
        key_mapping = progress.key_mapping

        orig_keys = sorted(
            d for d in os.listdir(att_dir)
            if os.path.isdir(os.path.join(att_dir, d))
        )

        logger.info(
            "Found %d issue directories in %s",
            len(orig_keys), att_dir,
        )

        total_ok = total_fail = total_skip = 0

        for orig_key in orig_keys:
            issue_dir = os.path.join(att_dir, orig_key)
            files = sorted(
                f for f in os.listdir(issue_dir)
                if os.path.isfile(os.path.join(issue_dir, f))
            )
            if not files:
                continue

            logger.info(
                "\n=== %s (%d file(s)) ===", orig_key, len(files),
            )

            # Resolve Cloud issue key
            cloud_key = key_mapping.get(orig_key)
            if not cloud_key:
                cloud_key = self._jql_lookup(
                    orig_key, project_key,
                )
            if not cloud_key:
                logger.warning(
                    "  Skipping %s — Cloud issue not found",
                    orig_key,
                )
                continue

            logger.info("  -> Cloud issue: %s", cloud_key)

            # Fetch existing attachments for dedup
            existing: set[str] = set()
            if skip_existing:
                existing = self._get_existing_filenames(cloud_key)
                logger.info(
                    "  Existing attachments: %d", len(existing),
                )

            for fname in files:
                file_path = os.path.join(issue_dir, fname)

                # Strip "id_" prefix from backup filenames
                clean_name = (
                    fname.split("_", 1)[-1]
                    if "_" in fname
                    else fname
                )

                if clean_name in existing:
                    logger.debug(
                        "    Skip (exists): %s", clean_name,
                    )
                    total_skip += 1
                    continue

                if dry_run:
                    logger.info(
                        "    [DRY] Would upload: %s -> %s",
                        clean_name, cloud_key,
                    )
                    total_ok += 1
                    continue

                try:
                    self.client.upload_file(
                        f"/rest/api/3/issue/{cloud_key}/attachments",
                        file_path,
                        filename=clean_name,
                    )
                    logger.info("    Uploaded: %s", clean_name)
                    total_ok += 1
                except (JiraApiError, Exception) as exc:
                    logger.error(
                        "    Failed %s: %s", clean_name, exc,
                    )
                    total_fail += 1

        logger.info(
            "\nDone — Uploaded: %d, Skipped: %d, Failed: %d",
            total_ok, total_skip, total_fail,
        )

    def _jql_lookup(
        self, orig_key: str, project_key: str,
    ) -> str | None:
        """Find Cloud issue by original key using JQL template."""
        template = self.config.legacy_key_jql_template
        if not template:
            return None

        jql = template.format(
            orig_key=orig_key, project_key=project_key,
        )
        logger.debug("  JQL lookup: %s", jql)

        try:
            result = self.client.post(
                "/rest/api/3/search/jql",
                {"jql": jql, "maxResults": 2, "fields": ["key"]},
            )
            issues = result.get("issues", [])
            if not issues:
                return None
            if len(issues) > 1:
                logger.warning(
                    "  Multiple issues found for %s, using first",
                    orig_key,
                )
            return issues[0]["key"]
        except JiraApiError as exc:
            logger.error(
                "  JQL search failed for %s: %s", orig_key, exc,
            )
            return None

    def _get_existing_filenames(
        self, cloud_key: str,
    ) -> set[str]:
        """Fetch filenames already attached to a Cloud issue."""
        try:
            data = self.client.get(
                f"/rest/api/3/issue/{cloud_key}",
                params={"fields": "attachment"},
            )
            attachments = (
                (data.get("fields") or {})
                .get("attachment") or []
            )
            return {
                a.get("filename", "")
                for a in attachments
                if a.get("filename")
            }
        except JiraApiError:
            return set()
